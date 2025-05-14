#!/bin/bash
apt update
apt install -y wget curl

# Install Playwright and Chromium properly
pip install --upgrade playwright
playwright install chromium --with-deps

# Set the Playwright browser path manually
export PLAYWRIGHT_BROWSERS_PATH=/opt/render/.cache/ms-playwright

# Verify Playwright installation
playwright --version

# Start Flask
python server.py