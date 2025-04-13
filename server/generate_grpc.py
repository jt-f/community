#!/usr/bin/env python3
"""
Script to generate gRPC Python code from protobuf definitions
"""
import os
import subprocess
import sys

def main():
    # Directory containing this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Define paths
    proto_dir = os.path.join(script_dir, "src", "protos")
    output_dir = os.path.join(script_dir, "src")
    proto_file = os.path.join(proto_dir, "agent_status_service.proto")
    
    # Ensure proto directory exists
    os.makedirs(proto_dir, exist_ok=True)
    
    # Check if the proto file exists
    if not os.path.exists(proto_file):
        print(f"Proto file not found: {proto_file}")
        return 1
    
    # Install required packages if not already installed
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "grpcio", "grpcio-tools", "protobuf"])
    except subprocess.CalledProcessError:
        print("Failed to install required packages.")
        return 1
    
    # Generate Python code from proto file
    try:
        cmd = [
            sys.executable, "-m", "grpc_tools.protoc", 
            f"-I{proto_dir}",
            f"--python_out={output_dir}",
            f"--grpc_python_out={output_dir}",
            proto_file
        ]
        subprocess.check_call(cmd)
        print(f"Successfully generated gRPC code from {proto_file}")
        
        # Create __init__.py files to make the generated code importable
        agent_status_dir = os.path.join(output_dir, "agent_status")
        os.makedirs(agent_status_dir, exist_ok=True)
        
        with open(os.path.join(agent_status_dir, "__init__.py"), "w") as f:
            pass
            
        print("Setup complete. gRPC code generated successfully!")
        return 0
    except subprocess.CalledProcessError:
        print("Failed to generate gRPC code.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 