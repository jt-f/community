#!/bin/bash

# Exit on error
set -e

# Build protos first
echo "Building protos..."
./build_protos.sh

# Run the server module
echo "Running server..."
python src/main.py "$@" 