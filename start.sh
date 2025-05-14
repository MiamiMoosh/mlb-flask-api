#!/bin/bash
apt update
apt install -y wget curl

# Install Google Chrome using Debian package (with proper dependency resolution)
wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb -O chrome.deb
dpkg -i chrome.deb || apt install -f -y  # Fix broken dependencies if needed

# Verify installation
which google-chrome
google-chrome --version

# Start Flask
python server.py