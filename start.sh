#!/bin/bash
apt update
apt install -y chromium

# Verify installation
which chromium
chromium --version

# Start Flask
python server.py