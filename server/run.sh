#!/bin/bash
if [ -f ~/.bashrc ]; then
  source ~/.bashrc
fi

# Exit on error
set -e

# Build protos first
echo "Building protos..."
./build_protos.sh

# Clear previous log file
echo "Clearing previous server log..."
rm -f /var/log/server.log

# Run the server module
echo "Running server..."
python src/main.py "$@" 