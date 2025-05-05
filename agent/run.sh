#!/bin/bash
source ~/.bashrc

# Exit on error
set -e

# Build protos first
echo "Building protos..."
pwd
ls -lrt

chmod +x ./build_protos.sh
./build_protos.sh


# Run the agent module
echo "Running agent..."
python src/agent.py "$@"