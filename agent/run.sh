#!/bin/bash
source ~/.bashrc

# Exit on error
set -e

# Build protos first
echo "Building protos..."
./build_protos.sh

# Run the agent module
echo "Running agent..."
poetry run python src/agent.py "$@" 