# ni-dataops containers

This repo contains builds of containers used in the ci-pipelines
To build these, it requires a docker-in-docker runner.
Any changes to Dockerfile or folder of a container should trigger a rebuild and push to gitlab registry.

## datalad-apptainer

A simple lightweight container (alpine-based) that contains datalad, datalad-containers and apptainer.
It's an apptainer-in-docker setup, which avoids caveats of using docker-in-docker (DinD), and allow to use community or custom containers made for rootless HPC usage.
That simple env allows notably to run ReproNim bids-app on bids repos but could also run other apptainer images.

## datalad-docker

Not currently used, replaced by datalad-apptainer.


## heudiconv

Container used for the dicom to BIDS conversion.

## deface

Custom defacing

## pydeface

Not currently used.
