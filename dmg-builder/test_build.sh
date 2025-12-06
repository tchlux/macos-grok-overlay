#!/bin/zsh

# Minimal local build (no signing/notarization)
set -euo pipefail

APP_NAME="macos-grok-overlay"

# Determine which architecture(s) to target (defaults to universal binary).
PY2APP_ARCH=${PY2APP_ARCH:-universal2}
case "$PY2APP_ARCH" in
    universal2)
        export ARCHFLAGS="-arch arm64 -arch x86_64"
        ;;
    arm64|x86_64)
        export ARCHFLAGS="-arch $PY2APP_ARCH"
        ;;
    *)
        echo "Unsupported PY2APP_ARCH value: $PY2APP_ARCH"
        echo "Use one of: arm64, x86_64, universal2."
        exit 1
        ;;
esac
echo "Local test build targeting architecture: $PY2APP_ARCH"

# source config.sh
touch temp.egg-info env dist build 2> /dev/null
rm -rf env dist build *.egg-info || echo 'Nothing to delete.'
python3 -m venv env
source env/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install setuptools==70.3.0 py2app pyobjc

pushd .. >/dev/null
# Build a full (non-alias) app so code signature stays valid.
python setup.py py2app --arch "$PY2APP_ARCH" --dist-dir="dmg-builder/dist" --bdist-base="dmg-builder/build"
# Ad-hoc sign just the bundle (skip strict validation on nested libs).
echo "Code signing the local .app so that permission settings work as expected."
codesign --force --sign - dmg-builder/dist/macos-grok-overlay.app

# Exit the directory.
popd >/dev/null


echo "Built app at dmg-builder/dist/${APP_NAME}.app"
