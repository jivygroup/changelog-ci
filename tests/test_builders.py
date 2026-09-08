import unittest
from unittest import mock

from scripts.builders import PullRequestChangelogBuilder, parse_version
from scripts.config import (
    LATEST_RELEASE,
    PREVIOUS_MINOR_RELEASE,
    ActionEnvironment,
    Configuration,
)

action_env = ActionEnvironment(
    event_path="",
    repository="test/test",
    pull_request_branch="",
    base_branch="",
    event_name="",
    event_payload={},
    github_workspace="",
)

# Ordered the way `GET /releases` returns them: newest published first.
# `3.4.1` ... `3.4.7` are hotfixes published *after* work for `3.5.0` began.
RELEASES = [
    {"tag_name": "3.4.7", "published_at": "2026-08-20T09:46:22Z", "draft": False},
    {"tag_name": "3.4.6", "published_at": "2026-08-18T10:55:07Z", "draft": False},
    {"tag_name": "3.4.5", "published_at": "2026-07-21T16:36:17Z", "draft": False},
    {"tag_name": "3.4.4", "published_at": "2026-07-13T13:07:41Z", "draft": False},
    {"tag_name": "3.4.3", "published_at": "2026-07-13T13:07:34Z", "draft": False},
    {"tag_name": "3.4.2", "published_at": "2026-06-14T13:48:24Z", "draft": False},
    {"tag_name": "3.4.1", "published_at": "2026-06-03T13:25:42Z", "draft": False},
    {"tag_name": "3.4.0", "published_at": "2026-05-28T15:58:09Z", "draft": False},
    {"tag_name": "3.3.0", "published_at": "2026-04-29T13:20:13Z", "draft": False},
]


def build(**overrides):
    config = Configuration(github_token="token", **overrides)
    return PullRequestChangelogBuilder(config, action_env, "3.5.0")


def fake_response(data, status_code=200):
    response = mock.Mock()
    response.status_code = status_code
    response.json.return_value = data
    return response


def fake_api(releases, latest=None, status_code=200):
    """Route `/releases/latest` and paginated `/releases` to distinct payloads

    The two endpoints return different shapes (an object vs. an array), and
    the pagination loop needs an empty page to terminate on.
    """

    def _get(url, *args, **kwargs):
        if status_code != 200:
            return fake_response(None, status_code=status_code)
        if "/search/issues" in url:
            return fake_response({"total_count": 0, "items": []})
        if "/releases/latest" in url:
            return fake_response(latest if latest is not None else {})
        if "page=1" in url:
            return fake_response(releases)
        return fake_response([])

    return _get


def search_url(get):
    """Return the URL of the pull request search call"""
    return next(
        call.args[0] for call in get.call_args_list if "/search/issues" in call.args[0]
    )


class TestParseVersion(unittest.TestCase):
    """Test the parse_version helper"""

    def test_parses_plain_and_prefixed_versions(self):
        self.assertEqual(parse_version("3.4.0"), (3, 4, 0))
        self.assertEqual(parse_version("v3.4.7"), (3, 4, 7))
        self.assertEqual(parse_version(" 3.10.2 "), (3, 10, 2))

    def test_rejects_non_versions(self):
        self.assertIsNone(parse_version("3.5"))
        self.assertIsNone(parse_version("release-3.4.0"))
        self.assertIsNone(parse_version("3.4.0-rc1"))
        self.assertIsNone(parse_version(""))

    def test_orders_numerically_not_lexically(self):
        self.assertGreater(parse_version("3.10.0"), parse_version("3.9.0"))


@mock.patch("scripts.builders.gha_utils")
class TestAnchorResolution(unittest.TestCase):
    """Test which release the changelog window is anchored on"""

    @mock.patch("scripts.builders.requests.get")
    def test_previous_minor_skips_interleaved_hotfixes(self, get, gha_utils):
        """The regression: hotfix releases must not become the anchor"""
        get.side_effect = fake_api(RELEASES, latest=RELEASES[0])

        builder = build(release_anchor=PREVIOUS_MINOR_RELEASE)

        # `3.4.7` is the most recently published release, but `3.4.0` is the
        # previous *minor* release and is the correct anchor for `3.5.0`.
        self.assertEqual(builder._get_anchor_release_date(), "2026-05-28T15:58:09Z")

    @mock.patch("scripts.builders.requests.get")
    def test_latest_remains_the_default(self, get, gha_utils):
        """Default behaviour is unchanged for repositories without hotfixes"""
        get.side_effect = fake_api(RELEASES, latest=RELEASES[0])

        builder = build()

        self.assertEqual(builder.config.release_anchor, LATEST_RELEASE)
        self.assertEqual(builder._get_anchor_release_date(), "2026-08-20T09:46:22Z")

    @mock.patch("scripts.builders.requests.get")
    def test_ignores_draft_releases(self, get, gha_utils):
        get.side_effect = fake_api(
            [
                {
                    "tag_name": "3.4.0",
                    "published_at": "2026-09-01T00:00:00Z",
                    "draft": True,
                },
                {
                    "tag_name": "3.3.0",
                    "published_at": "2026-04-29T13:20:13Z",
                    "draft": False,
                },
            ]
        )

        builder = build(release_anchor=PREVIOUS_MINOR_RELEASE)

        self.assertEqual(builder._get_anchor_release_date(), "2026-04-29T13:20:13Z")

    @mock.patch("scripts.builders.requests.get")
    def test_falls_back_when_no_previous_minor_exists(self, get, gha_utils):
        """A first-ever minor release has no anchor below it"""
        get.side_effect = fake_api(
            [{"tag_name": "3.5.0", "published_at": "2026-09-01T00:00:00Z"}],
            latest={"published_at": "2026-09-01T00:00:00Z"},
        )

        builder = build(release_anchor=PREVIOUS_MINOR_RELEASE)

        # Falls back to `/releases/latest`, which the same mock answers.
        self.assertEqual(builder._get_anchor_release_date(), "2026-09-01T00:00:00Z")
        gha_utils.warning.assert_called()

    @mock.patch("scripts.builders.requests.get")
    def test_falls_back_when_release_version_is_unparseable(self, get, gha_utils):
        get.side_effect = fake_api(RELEASES, latest=RELEASES[0])

        config = Configuration(
            github_token="token", release_anchor=PREVIOUS_MINOR_RELEASE
        )
        builder = PullRequestChangelogBuilder(config, action_env, "not-a-version")

        self.assertEqual(builder._get_anchor_release_date(), "2026-08-20T09:46:22Z")
        gha_utils.warning.assert_called()

    @mock.patch("scripts.builders.requests.get")
    def test_stops_paginating_on_error(self, get, gha_utils):
        get.side_effect = fake_api([], status_code=403)

        builder = build(release_anchor=PREVIOUS_MINOR_RELEASE)

        self.assertEqual(builder._get_anchor_release_date(), "")
        gha_utils.warning.assert_called()


@mock.patch("scripts.builders.gha_utils")
class TestBaseBranchFilter(unittest.TestCase):
    """Test that the pull request search is restricted by target branch"""

    @mock.patch("scripts.builders.requests.get")
    def test_base_branches_are_added_to_the_query(self, get, gha_utils):
        get.side_effect = fake_api(RELEASES, latest=RELEASES[0])

        build(
            base_branches=["develop", "release/3.5.0"]
        )._get_changes_after_last_release()

        url = search_url(get)
        self.assertIn("base:develop+", url)
        self.assertIn("base:release/3.5.0+", url)

    @mock.patch("scripts.builders.requests.get")
    def test_no_base_filter_by_default(self, get, gha_utils):
        get.side_effect = fake_api(RELEASES, latest=RELEASES[0])

        build()._get_changes_after_last_release()

        self.assertNotIn("base:", search_url(get))


if __name__ == "__main__":
    unittest.main()
