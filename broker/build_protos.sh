#!/bin/bash

# Exit on error
set -e

# Ensure we're in the right directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Create generated directory if it doesn't exist
mkdir -p src/generated

# Generate Python gRPC files
python -m grpc_tools.protoc \
    -I/app/shared/protos \
    --python_out=src/generated \
    --grpc_python_out=src/generated \
    /app/shared/protos/*.proto

# Fix imports in generated files
for file in src/generated/*.py; do
    # Get the module name from the file path
    MODULE_NAME=$(basename "$(dirname "$(dirname "$file")")")
    sed -i "s/^import \(.*\)_pb2/from $MODULE_NAME.generated import \1_pb2/" "$file"
done

echo "gRPC files generated successfully in src/generated/" 