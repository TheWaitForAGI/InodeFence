FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3.12 \
        python3.12-venv \
        python3-pip \
        build-essential \
        git \
        tar \
        gzip \
        xz-utils \
        file \
        jq \
        strace \
    && rm -rf /var/lib/apt/lists/*

RUN python3.12 -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install --upgrade \
        pip \
        setuptools \
        wheel \
    && chown -R vscode:vscode /opt/venv

ENV PATH="/opt/venv/bin:${PATH}"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV INODEFENCE_RUNTIME_ROOT="/var/lib/inodefence"
