#!/bin/bash
apt update
apt install -y wget curl

# Ensure Playwright browsers are installed
pip install --upgrade playwright
playwright install --with-deps

# Verify Playwright installation
playwright --version

# Start Flask
python server.py