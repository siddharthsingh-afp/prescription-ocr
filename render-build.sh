#!/usr/bin/env bash
# Exit on error
set -o errexit

# Install system dependencies for Pillow
apt-get update
apt-get install -y libjpeg-dev zlib1g-dev

# Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt