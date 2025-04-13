#!/usr/bin/env python3
"""
Script to generate gRPC Python code from protobuf definitions
"""
import os
import subprocess
import sys
import re

def main():
    # Directory containing this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Define paths
    proto_dir = os.path.join(script_dir, "src", "protos")
    generated_dir = os.path.join(script_dir, "generated")
    output_dir = generated_dir
    proto_file = os.path.join(proto_dir, "agent_status_service.proto")
    
    # Ensure directories exist
    os.makedirs(proto_dir, exist_ok=True)
    os.makedirs(generated_dir, exist_ok=True)
    
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
        
        # Fix the import statement in the generated _pb2_grpc.py file
        pb2_grpc_file = os.path.join(output_dir, "agent_status_service_pb2_grpc.py")
        if os.path.exists(pb2_grpc_file):
            print(f"Fixing import statement in {pb2_grpc_file}")
            with open(pb2_grpc_file, 'r') as file:
                content = file.read()
            
            # Replace the import statement with a relative import that doesn't depend on Python package paths
            fixed_content = re.sub(
                r'import agent_status_service_pb2 as agent__status__service__pb2',
                r'from . import agent_status_service_pb2 as agent__status__service__pb2',
                content
            )
            
            with open(pb2_grpc_file, 'w') as file:
                file.write(fixed_content)
            
            print(f"Fixed import statement in {pb2_grpc_file}")
        
        # Create __init__.py file in the generated directory to make it a package
        with open(os.path.join(generated_dir, "__init__.py"), "w") as f:
            pass
            
        print("Setup complete. gRPC code generated successfully!")
        return 0
    except subprocess.CalledProcessError:
        print("Failed to generate gRPC code.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 