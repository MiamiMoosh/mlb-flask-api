#!/bin/bash
# Install Chrome manually
apt update
apt install -y chromium-browser
which chromium-browser

# Start Flask
python server.py