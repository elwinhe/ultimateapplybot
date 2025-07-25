#!/bin/bash

# Clean up any leftover lock files from previous runs
rm -f /tmp/.X99-lock

# Set the display environment variable
export DISPLAY=:99

# Start Xvfb in the background
Xvfb :99 -screen 0 1280x960x24 &
XVFB_PID=$!

# Wait for Xvfb to be ready before starting other applications
sleep 2

# Start a window manager in the background
fluxbox &
FLUXBOX_PID=$!

# Start the VNC server in the background
x11vnc -display :99 -nopw -forever -ncache 10 -verbose &
VNC_PID=$!

# Define a cleanup function to be called on exit
cleanup() {
    echo "Cleaning up background processes..."
    kill $VNC_PID
    kill $FLUXBOX_PID
    kill $XVFB_PID
}

# Trap the exit signal to ensure the cleanup function is called
trap cleanup EXIT

# Run the main Python application in the foreground
# The script will wait here until the python app finishes
python main.py 