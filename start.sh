#!/bin/bash
apt update
apt install -y wget curl

# Download & Install Google Chrome
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
apt install -y ./google-chrome-stable_current_amd64.deb

# Verify installation
which google-chrome
google-chrome --version

# Start Flask
python server.py