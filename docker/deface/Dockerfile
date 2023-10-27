FROM python:3.8-slim

RUN apt-get update \
  && apt-get -y install git git-annex build-essential\
  && apt-get autoremove && apt-get clean && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/courtois-neuromod/ds_prep.git && \
  cd ds_prep && git checkout gitlab &&  \
  pip install --no-cache-dir packaging datalad && \
  pip install --no-cache-dir -r requirements.txt
RUN git config --global user.name docker_bot && \
  git config --global user.email docket_bot@dummy.net
RUN cd /ds_prep && \
  datalad get global/templates/*.nii.gz
