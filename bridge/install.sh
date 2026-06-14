#!/bin/bash
set -e

INSTALL_DIR=/opt/nanokvm-bridge
SERVICE_NAME=nanokvm-bridge

echo "Installing NanoKVM-USB bridge..."

# Install system dependencies
sudo apt-get update -qq
sudo apt-get install -y ffmpeg python3-pip python3-aiohttp

# Install Python dependencies
pip3 install -r "$(dirname "$0")/requirements.txt"

# Copy files to install dir
sudo mkdir -p "$INSTALL_DIR"
sudo cp "$(dirname "$0")/bridge.py" "$INSTALL_DIR/"
sudo cp "$(dirname "$0")/requirements.txt" "$INSTALL_DIR/"

# Add current user to dialout group for serial port access
sudo usermod -aG dialout "$USER"

# Install and enable systemd service
sudo cp "$(dirname "$0")/nanokvm-bridge.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl start "$SERVICE_NAME"

echo ""
echo "Bridge installed and started."
echo "  Video stream: http://$(hostname -I | awk '{print $1}'):8080/video"
echo "  Serial WS:    ws://$(hostname -I | awk '{print $1}'):8080/serial"
echo ""
echo "NOTE: Log out and back in for serial port group permissions to take effect."
echo "      To change ports/devices, edit /etc/systemd/system/nanokvm-bridge.service"
