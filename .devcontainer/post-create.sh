#!/usr/bin/env bash
set -euo pipefail

sudo chown -R vscode:vscode /var/lib/inodefence
sudo chown -R vscode:vscode /home/vscode/.codex

python -m pip install -e '.[dev]'

npm install --global @openai/codex@latest

python --version
node --version
npm --version
codex --version
