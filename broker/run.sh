#!/bin/bash
source ~/.bashrc
# Exit on error
set -e

# Build protos first
echo "Building protos..."
./build_protos.sh

# Run the broker module
echo "Running broker..."
python src/broker.py "$@" 