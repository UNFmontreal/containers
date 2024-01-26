FROM alpine:3.19
RUN apk add --no-cache ca-certificates tzdata \
    python3 py3-pip git openssh-client git-annex curl bzip2 bash glab\
    && cp /usr/share/zoneinfo/UTC /etc/localtime \
    && apk del tzdata \
    && rm -rf /tmp/* /var/cache/apk/*
RUN apk add --no-cache dcmtk --repository=https://dl-cdn.alpinelinux.org/alpine/edge/testing


RUN pip install --break-system-packages --no-cache-dir datalad ssh_agent_setup python-gitlab pydicom pyyaml

ADD indexer /indexer

WORKDIR /work
