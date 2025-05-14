#!/bin/bash
apt update
apt install -y chromium-browser || apt install -y chromium

# Debugging verification
which chromium-browser || which chromium
chromium-browser --version || chromium --version

# Start Flask
python server.py
