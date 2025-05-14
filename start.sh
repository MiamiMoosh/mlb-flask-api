#!/bin/bash
apt update
apt install -y wget curl

# Install Playwright browsers
pip install --upgrade playwright
playwright install --with-deps

# Start Flask
python server.py