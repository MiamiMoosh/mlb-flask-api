#!/bin/bash
apt update

# Print system information
echo "OS Version:"
cat /etc/os-release

# List available package managers
echo "Checking package managers:"
command -v apt
command -v yum
command -v apk

# Install dependencies for Chrome
apt install -y wget curl

# Install Google Chrome via Debian package
wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb -O chrome.deb
dpkg -i chrome.deb || apt install -f -y

# Verify installation
which google-chrome
google-chrome --version

# Start Flask
python server.py