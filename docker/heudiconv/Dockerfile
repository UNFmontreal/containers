FROM python:3.10-slim

RUN apt-get update \
  && apt-get -y install 7zip curl git git-annex dcm2niix \
  && apt-get autoremove && apt-get clean && rm -rf /var/lib/apt/lists/*

ARG GLAB_VERSION=1.25.3
RUN curl -O -L https://gitlab.com/gitlab-org/cli/-/releases/v${GLAB_VERSION}/downloads/glab_${GLAB_VERSION}_Linux_x86_64.deb \
  && dpkg -i glab_${GLAB_VERSION}_Linux_x86_64.deb \
  && rm -f glab_${GLAB_VERSION}_Linux_x86_64.deb
RUN ln -s /usr/bin/7zz /usr/bin/7z

RUN pip install --no-cache-dir frozendict bids datalad
RUN pip install --no-cache-dir git+https://github.com/UNFmontreal/heudiconv@unf_prod
