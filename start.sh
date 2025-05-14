#!/bin/bash
apt update
apt install -y wget curl

# Install Google Chrome the official way
wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb -O chrome.deb
apt install -y ./chrome.deb

# Verify installation
which google-chrome
google-chrome --version

# Start Flask
python server.py