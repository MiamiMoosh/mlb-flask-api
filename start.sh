#!/bin/bash
apt update
apt install -y wget curl

# Install Playwright and browsers before starting the app
pip install --upgrade playwright
playwright install chromium --with-deps

# Verify Playwright installation
playwright --version

# Start Flask
python server.py