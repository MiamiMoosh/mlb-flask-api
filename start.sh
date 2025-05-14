#!/bin/bash
apt update

# Install dependencies
apt install -y wget curl gnupg

# Add Google's signing key and repository
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | tee /etc/apt/sources.list.d/google-chrome.list

# Update package list and install Chrome
apt update
apt install -y google-chrome-stable

# Verify installation
which google-chrome
google-chrome --version

# Start Flask
python server.py