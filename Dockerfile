FROM python:3.12-slim-bookworm

LABEL "com.github.actions.name"="Changelog CI"
LABEL "com.github.actions.description"="Changelog CI is a GitHub Action that generates changelog, Then the changelog is committed and/or commented to the release Pull request."
LABEL "com.github.actions.icon"="clock"
LABEL "com.github.actions.color"="blue"

LABEL "repository"="https://github.com/jivygroup/changelog-ci"
LABEL "homepage"="https://github.com/jivygroup/changelog-ci"
LABEL "maintainer"="jivygroup"
LABEL "org.opencontainers.image.source"="https://github.com/jivygroup/changelog-ci"
LABEL "org.opencontainers.image.licenses"="MIT"
LABEL "org.opencontainers.image.description"="Fork of saadmk11/changelog-ci (MIT). See NOTICE."

RUN apt-get update \
    && apt-get install \
       -y \
       --no-install-recommends \
       --no-install-suggests \
       git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY ./requirements.txt .

RUN pip install -r requirements.txt

COPY . ./app

ENV PYTHONPATH "${PYTHONPATH}:/app"

CMD ["python", "-m", "scripts.main"]
