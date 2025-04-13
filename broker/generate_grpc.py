#!/usr/bin/env python3
"""
Script to generate gRPC Python code from protobuf definitions for the broker
"""
import os
import subprocess
import sys
import shutil
import re

def main():
    # Directory containing this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Define paths
    proto_dir = os.path.join(script_dir, "src", "protos")
    generated_dir = os.path.join(script_dir, "generated")
    output_dir = generated_dir
    
    # First, check if proto file exists in the server directory
    server_proto_dir = os.path.join(script_dir, "..", "server", "src", "protos")
    server_proto_file = os.path.join(server_proto_dir, "agent_status_service.proto")
    local_proto_file = os.path.join(proto_dir, "agent_status_service.proto")
    
    # Create proto directory if it doesn't exist
    os.makedirs(proto_dir, exist_ok=True)
    
    # Create generated directory if it doesn't exist
    os.makedirs(generated_dir, exist_ok=True)
    
    # Copy proto file from server to broker if it exists
    if os.path.exists(server_proto_file):
        print(f"Copying proto file from server: {server_proto_file}")
        shutil.copy2(server_proto_file, local_proto_file)
    else:
        print(f"Warning: Proto file not found in server directory: {server_proto_file}")
        # Check if we need to create the proto definition locally
        if not os.path.exists(local_proto_file):
            print(f"Creating proto file locally: {local_proto_file}")
            with open(local_proto_file, "w") as f:
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
    
    # Install required packages if not already installed
    try:
        print("Installing required packages...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "grpcio", "grpcio-tools", "protobuf"])
    except subprocess.CalledProcessError:
        print("Failed to install required packages.")
        return 1
    
    # Generate Python code from proto file
    try:
        # Ensure the proto file exists
        if not os.path.exists(local_proto_file):
            print(f"Error: Proto file not found: {local_proto_file}")
            return 1
            
        print(f"Generating Python code from {local_proto_file}...")
        cmd = [
            sys.executable, "-m", "grpc_tools.protoc", 
            f"-I{proto_dir}",
            f"--python_out={output_dir}",
            f"--grpc_python_out={output_dir}",
            local_proto_file
        ]
        subprocess.check_call(cmd)
        print(f"Successfully generated gRPC code from {local_proto_file}")
        
        # Check if the generated files exist
        pb2_file = os.path.join(output_dir, "agent_status_service_pb2.py")
        pb2_grpc_file = os.path.join(output_dir, "agent_status_service_pb2_grpc.py")
        
        if not os.path.exists(pb2_file) or not os.path.exists(pb2_grpc_file):
            print(f"Error: Generated files not found. Expected at {pb2_file} and {pb2_grpc_file}")
            return 1
            
        print(f"Generated files created successfully: {pb2_file}, {pb2_grpc_file}")
        
        # Fix the import statement in the generated _pb2_grpc.py file
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