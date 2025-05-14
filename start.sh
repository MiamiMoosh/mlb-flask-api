#!/bin/bash
apt update
apt install -y wget curl

# Install Google Chrome via a Debian package
wget https://dl.google.com/linux/chrome/deb/pool/main/g/google-chrome-stable/google-chrome-stable_123.0.1234.56-1_amd64.deb -O chrome.deb
apt install -y ./chrome.deb

# Verify installation
which google-chrome
google-chrome --version

# Start Flask
python server.py