FROM alpine:3.17.2
RUN apk add --no-cache ca-certificates tzdata \
    python3 py3-pip git openssh-client git-annex curl bzip2 bash glab\
    && cp /usr/share/zoneinfo/UTC /etc/localtime \
    && apk del tzdata \
    && rm -rf /tmp/* /var/cache/apk/*

RUN pip install --no-cache-dir datalad ssh_agent_setup python-gitlab pydicom

WORKDIR /work
