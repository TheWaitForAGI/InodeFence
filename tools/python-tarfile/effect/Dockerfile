# python-tarfile effect producer image: the official runtime image plus one worker file.
#
# BASE is the already-prepared, version-verified official image (python:X.Y.Z-slim, resolved and
# checked by the python-tarfile target's prepare step). Nothing is installed and no RUN step
# executes, so the build needs no network; the image adds only /target/worker.py (standard
# library only). Built from a temporary context outside the repository; see
# scripts/python_tarfile_producer.py.
ARG BASE
FROM ${BASE}
COPY worker.py /target/worker.py
