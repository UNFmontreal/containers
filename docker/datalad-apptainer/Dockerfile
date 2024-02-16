FROM golang:1.21.5-alpine3.19 as builder

RUN apk add --no-cache \
        # Required for apptainer to find min go version
        bash \
        cryptsetup \
        gawk \
        gcc \
        git \
        libc-dev \
        linux-headers \
        libressl-dev \
        libuuid \
        libseccomp-dev \
        make \
        util-linux-dev

ARG APPTAINER_COMMITISH="main"
ARG MCONFIG_OPTIONS="--with-suid"
WORKDIR $GOPATH/src/github.com/apptainer
RUN git clone https://github.com/apptainer/apptainer.git \
    && cd apptainer \
    && git checkout "$APPTAINER_COMMITISH" \
    && ./mconfig $MCONFIG_OPTIONS -p /usr/local/apptainer \
    && cd builddir \
    && make \
    && make install

FROM alpine:3.19
COPY --from=builder /usr/local/apptainer /usr/local/apptainer
ENV PATH="/usr/local/apptainer/bin:$PATH" \
    APPTAINER_TMPDIR="/tmp-apptainer"
RUN apk add --no-cache py3-pytest ca-certificates libseccomp squashfs-tools tzdata fuse2fs fuse-overlayfs squashfuse \
    python3 py3-pip git openssh-client git-annex curl bzip2 bash glab\
    && mkdir -p $APPTAINER_TMPDIR \
    && cp /usr/share/zoneinfo/UTC /etc/localtime \
    && apk del tzdata \
    && rm -rf /tmp/* /var/cache/apk/*

RUN pip install --break-system-packages --no-cache-dir datalad datalad-container ssh_agent_setup python-gitlab
ADD cfg_nidataops.py /usr/lib/python3.11/site-packages/datalad/resources/procedures/

WORKDIR /work
