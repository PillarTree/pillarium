#!/bin/sh
# Install the Pillarium development dependencies.
set -e
python3 -m venv .venv
. .venv/bin/activate
pip3 install -r requirements.txt
echo "Installed Pillarium successfully!"
