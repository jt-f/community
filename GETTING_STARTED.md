# Getting Started Guide

This guide will help you quickly set up and run the Agent Communication System using Docker Compose.

## Prerequisites

- Docker and Docker Compose installed
  - The system is developed and tested with Docker Compose V2
- Python 3.13.2+ and Poetry for running agents
  - The system is developed and tested with Python 3.13.2
  - [pyenv](https://github.com/pyenv/pyenv) is recommended for managing Python versions
- Git (to clone the repository)

## Installing Docker and Docker Compose

### Windows and Mac

The easiest way to install Docker and Docker Compose on Windows or Mac is to download and install Docker Desktop:

1. Download [Docker Desktop](https://www.docker.com/products/docker-desktop)
2. Follow the installation instructions for your operating system
3. Docker Compose is included with Docker Desktop

### Linux

On Linux, you'll need to install Docker Engine and Docker Compose separately:

1. Install Docker Engine:
   ```bash
   # Update package index
   sudo apt-get update

   # Install required packages
   sudo apt-get install ca-certificates curl gnupg

   # Add Docker's official GPG key
   sudo install -m 0755 -d /etc/apt/keyrings
   curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
   sudo chmod a+r /etc/apt/keyrings/docker.gpg

   # Set up the repository
   echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

   # Update packages again
   sudo apt-get update

   # Install Docker Engine
   sudo apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
   ```

2. Install Docker Compose:
   ```bash
   sudo apt-get install docker-compose-plugin
   ```

## Installing Python and Poetry

1. Install Python 3.13.2 using pyenv:
   ```bash
   pyenv install 3.13.2
   pyenv global 3.13.2
   ```

2. Install Poetry:
   ```bash
   curl -sSL https://install.python-poetry.org | python3 -
   ```

## Setting Up the Project

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd community
   ```

2. Install dependencies for each service:
   ```bash
   cd agent && poetry install && cd ..
   cd broker && poetry install && cd ..
   cd server && poetry install && cd ..
   ```

3. Build the gRPC code for each service:
   ```bash
   cd agent && ./build_protos.sh && cd ..
   cd broker && ./build_protos.sh && cd ..
   cd server && ./build_protos.sh && cd ..
   ```

## Running the System

1. Start the core infrastructure:
   ```bash
   docker compose up --build
   ```

2. In a new terminal, run an agent:
   ```bash
   # Option 1: Running directly with Poetry
   cd agent
   poetry run ./run.sh --name "MyAgent"
   
   ```

   Note: Agents can be run only directly with Poetry/Python.

3. Access the web interface at http://localhost:5173

## Development Workflow

### Modifying Proto Definitions

1. Edit the proto files in `shared/protos/`
2. Rebuild gRPC code for affected services:
   ```bash
   cd <service_directory>
   ./build_protos.sh
   ```

### Running Services Locally

Each service can be run locally using its run script:

```bash
cd <service_directory>
./run.sh [arguments]
```

### Docker Development

When developing with Docker:

1. The shared proto files are mounted into each container
2. gRPC code is generated during the build process
3. Changes to proto files require rebuilding the affected containers:
   ```bash
   docker compose build <service_name>
   docker compose up -d <service_name>
   ```

## Troubleshooting

If you encounter issues:

1. Check the Docker logs:
   ```bash
   docker compose logs
   ```

2. Verify gRPC code generation:
   ```bash
   cd <service_directory>
   ./build_protos.sh
   ```

3. Check service dependencies:
   ```bash
   docker compose ps
   ```

## Environment Variables for Agents

For agents that connect to external services (like Mistral AI), you'll need to set environment variables:

```bash
# Create a .env file in the agent directory
echo "MISTRAL_API_KEY=your_api_key_here" > agent/.env

# Or set the environment variable directly
export MISTRAL_API_KEY=your_api_key_here
```

## Next Steps

- Check the individual README files for each component for more details
- Explore customizing agents for specific tasks
- Review the architecture diagram to understand system communication flow 