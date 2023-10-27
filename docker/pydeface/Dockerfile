FROM nipreps/fmriprep:unstable as fsl_source

FROM python:3.10-slim

COPY --from=fsl_source  /opt/conda/envs/fmriprep/bin/flirt /opt/fsl/bin/

COPY --from=fsl_source /opt/conda/envs/fmriprep/lib/libquadmath.so.0.0.0 /opt/fsl/lib/
COPY --from=fsl_source /opt/conda/envs/fmriprep/lib/libgfortran.so.5.0.0 /opt/fsl/lib/
COPY --from=fsl_source /opt/conda/envs/fmriprep/lib/libfsl-NewNifti.so /opt/fsl/lib/
COPY --from=fsl_source /opt/conda/envs/fmriprep/lib/libfsl-cprob.so /opt/fsl/lib/
COPY --from=fsl_source /opt/conda/envs/fmriprep/lib/libfsl-miscmaths.so /opt/fsl/lib/
COPY --from=fsl_source /opt/conda/envs/fmriprep/lib/libfsl-newimage.so /opt/fsl/lib/
COPY --from=fsl_source /opt/conda/envs/fmriprep/lib/libfsl-utils.so /opt/fsl/lib/
COPY --from=fsl_source /opt/conda/envs/fmriprep/lib/libfsl-znz.so /opt/fsl/lib/
COPY --from=fsl_source /opt/conda/envs/fmriprep/lib/libgcc_s.so.1 /opt/fsl/lib/
COPY --from=fsl_source /opt/conda/envs/fmriprep/lib/libopenblasp-r0.3.23.so /opt/fsl/lib/
COPY --from=fsl_source /opt/conda/envs/fmriprep/lib/libstdc++.so.6.0.31 /opt/fsl/lib/
COPY --from=fsl_source /opt/conda/envs/fmriprep/lib/libz.so.1.2.13 /opt/fsl/lib/

RUN ln -s libopenblasp-r0.3.23.so /opt/fsl/lib/liblapack.so.3
RUN ln -s libopenblasp-r0.3.23.so /opt/fsl/lib/libblas.so.3
RUN ln -s libquadmath.so.0.0.0 /opt/fsl/lib/libquadmath.so.0
RUN ln -s libgfortran.so.5.0.0 /opt/fsl/lib/libgfortran.so.5
RUN ln -s libstdc++.so.6.0.31 /opt/fsl/lib/libstdc++.so.6
RUN ln -s libz.so.1.2.13 /opt/fsl/lib/libz.so.1

ENV LD_LIBRARY_PATH=/opt/fsl/lib

RUN pip --no-cache-dir install pydeface
ENV PATH=$PATH:/opt/fsl/bin
ENV FSLDIR=/opt/fsl/bin
RUN sed -i "s/shutil.which('fsl')/shutil.which('flirt')/g" /usr/local/lib/python3.10/site-packages/pydeface/utils.py
