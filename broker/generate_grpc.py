#!/usr/bin/env python3
"""
Script to generate gRPC Python code from protobuf definitions for the broker
"""
import os
import subprocess
import sys
import shutil
import re
import glob

def main():
    # Directory containing this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Define paths
    proto_dir = os.path.join(script_dir, "src", "protos")
    generated_dir = os.path.join(script_dir, "generated")
    output_dir = generated_dir
    
    # Create directories if they don't exist
    os.makedirs(proto_dir, exist_ok=True)
    os.makedirs(generated_dir, exist_ok=True)
    
    # Copy proto files from server to broker
    server_proto_dir = os.path.join(script_dir, "..", "server", "src", "protos")
    
    # Get all proto files from server
    server_proto_files = glob.glob(os.path.join(server_proto_dir, "*.proto"))
    
    if not server_proto_files:
        print(f"Warning: No proto files found in server directory: {server_proto_dir}")
        # Generate default agent status proto if no files found
        default_proto_file = os.path.join(proto_dir, "agent_status_service.proto")
        if not os.path.exists(default_proto_file):
            print(f"Creating default proto file: {default_proto_file}")
            with open(default_proto_file, "w") as f:
                f.write("""syntax = "proto3";

package agent_status;

// Define the service for agent status updates
service AgentStatusService {
  // Request initial agent status and subscribe to future updates
  rpc SubscribeToAgentStatus (AgentStatusRequest) returns (stream AgentStatusResponse) {}
  
  // Request a one-time full agent status update
  rpc GetAgentStatus (AgentStatusRequest) returns (AgentStatusResponse) {}
}

// Request message for agent status
message AgentStatusRequest {
  string broker_id = 1;  // ID of the requesting broker
}

// Response message containing agent status information
message AgentStatusResponse {
  repeated AgentInfo agents = 1;
  bool is_full_update = 2;  // Whether this is a complete agent list or just updates
}

// Information about an individual agent
message AgentInfo {
  string agent_id = 1;
  string agent_name = 2;
  bool is_online = 3;
  string last_seen = 4;  // ISO format timestamp
}
""")
    else:
        # Copy all proto files from server to broker
        for server_proto_file in server_proto_files:
            local_proto_file = os.path.join(proto_dir, os.path.basename(server_proto_file))
            print(f"Copying proto file from server: {server_proto_file}")
            shutil.copy2(server_proto_file, local_proto_file)
    
    # Get all proto files in the broker's proto directory
    proto_files = glob.glob(os.path.join(proto_dir, "*.proto"))
    
    if not proto_files:
        print(f"No proto files found in: {proto_dir}")
        return 1
    
    # Install required packages if not already installed
    try:
        print("Installing required packages...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "grpcio", "grpcio-tools", "protobuf"])
    except subprocess.CalledProcessError:
        print("Failed to install required packages.")
        return 1
    
    # Generate Python code from proto files
    try:
        for proto_file in proto_files:
            print(f"Processing proto file: {proto_file}")
            
            # Check if the proto file exists
            if not os.path.exists(proto_file):
                print(f"Error: Proto file not found: {proto_file}")
                continue
                
            print(f"Generating Python code from {proto_file}...")
            cmd = [
                sys.executable, "-m", "grpc_tools.protoc", 
                f"-I{proto_dir}",
                f"--python_out={output_dir}",
                f"--grpc_python_out={output_dir}",
                proto_file
            ]
            subprocess.check_call(cmd)
            print(f"Successfully generated gRPC code from {proto_file}")
            
            # Get the base filename without extension
            base_filename = os.path.basename(proto_file).replace(".proto", "")
            
            # Check if the generated files exist
            pb2_file = os.path.join(output_dir, f"{base_filename}_pb2.py")
            pb2_grpc_file = os.path.join(output_dir, f"{base_filename}_pb2_grpc.py")
            
            if not os.path.exists(pb2_file) or not os.path.exists(pb2_grpc_file):
                print(f"Error: Generated files not found. Expected at {pb2_file} and {pb2_grpc_file}")
                continue
                
            print(f"Generated files created successfully: {pb2_file}, {pb2_grpc_file}")
            
            # Fix the import statement in the generated _pb2_grpc.py file
            if os.path.exists(pb2_grpc_file):
                print(f"Fixing import statement in {pb2_grpc_file}")
                with open(pb2_grpc_file, 'r') as file:
                    content = file.read()
                
                # Replace the import statement with a relative import that doesn't depend on Python package paths
                fixed_content = re.sub(
                    rf'import {base_filename}_pb2 as {base_filename.replace("_", "__")}__pb2',
                    rf'from . import {base_filename}_pb2 as {base_filename.replace("_", "__")}__pb2',
                    content
                )
                
                with open(pb2_grpc_file, 'w') as file:
                    file.write(fixed_content)
                
                print(f"Fixed import statement in {pb2_grpc_file}")
        
        # Create __init__.py file in the generated directory to make it a package
        init_file = os.path.join(generated_dir, "__init__.py")
        with open(init_file, "w") as f:
            pass
        print(f"Created __init__.py in the generated directory: {init_file}")
        
        print("Setup complete. gRPC code generated successfully!")
        return 0
    except subprocess.CalledProcessError as e:
        print(f"Failed to generate gRPC code: {e}")
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 