#!/bin/zsh

# Minimal local build (no signing/notarization)
set -euo pipefail

APP_NAME="macos-grok-overlay"

touch temp.egg-info
rm -rf env dist build *.egg-info || echo 'Nothing to delete.'
python3 -m venv env
source env/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install setuptools==70.3.0 py2app pyobjc

pushd .. >/dev/null
# Build py2app with "-A" that uses local python environment.
python setup.py py2app -A --dist-dir="dmg-builder/dist" --bdist-base="dmg-builder/build"
popd >/dev/null

echo "Built app at dmg-builder/dist/${APP_NAME}.app"
