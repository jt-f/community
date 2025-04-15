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

2. Verify the installation:
   ```bash
   sudo docker run hello-world
   ```

3. Configure Docker to run without sudo (optional):
   ```bash
   sudo groupadd docker
   sudo usermod -aG docker $USER
   # Log out and log back in for changes to take effect
   ```

4. Docker Compose V2 is included as a plugin with Docker Engine. Verify it's working:
   ```bash
   docker compose version
   ```

For other Linux distributions or more details, see the [official Docker documentation](https://docs.docker.com/engine/install/).

## Quick Start

### 1. Clone the Repository (if you haven't already)

```bash
git clone https://github.com/yourusername/community.git
cd community
```

### 2. Start Core Infrastructure

The simplest way to get started is to use Docker Compose to start all the core components:

```bash
# Build and start all core services
docker compose up --build
```

This will:
- Start RabbitMQ message broker
- Start the server component
- Start the message routing broker
- Start the frontend application

Once everything is up and running, you can access:
- The web frontend at: http://localhost:5173
- RabbitMQ Management UI at: http://localhost:15673 (login: guest/guest)

### 3. Start an Agent

Agents are run separately to allow for dynamic configuration and flexibility. Open a new terminal:

```bash
cd agent

# Make sure you're using Python 3.13.2+
# If using pyenv:
pyenv install 3.13.2  # if not already installed
pyenv local 3.13.2

# Install Poetry if not already installed
# curl -sSL https://install.python-poetry.org | python3 -

# Install dependencies (first time only)
poetry install

# Run an agent
poetry run python src/agent.py --name "MyFirstAgent"
```

You can start multiple agents in different terminals, each with a unique name.

### 4. Using the System

1. Open the web frontend at http://localhost:5173
2. You should see your agent(s) listed in the agent directory
3. Click on an agent to start a conversation
4. Type a message and press Enter to send it to the agent
5. The agent will process the message and send a response

## Environment Variables for Agents

For agents that connect to external services (like Mistral AI), you'll need to set environment variables:

```bash
# Create a .env file in the agent directory
echo "MISTRAL_API_KEY=your_api_key_here" > agent/.env

# Or set the environment variable directly
export MISTRAL_API_KEY=your_api_key_here
```

## Troubleshooting

### Poetry Configuration

If you encounter errors about Poetry configuration being invalid, ensure:
- Your Poetry is up to date (`poetry self update`)
- The pyproject.toml file has the correct format, especially for the authors field

### Port Conflicts

If you see errors about ports already in use, you may need to modify the port mappings in compose.yaml or stop other services using those ports.

### Agent Connectivity

If agents can't connect to the server or RabbitMQ:
- Ensure the core infrastructure is fully started before launching agents
- Check that your firewall isn't blocking the required ports
- Verify you're running the agent with the correct environment variables

### Docker Issues

If Docker Compose fails to build or start the services:
- Try running `docker compose down` and then `docker compose up --build` again
- Check Docker logs for specific error messages

## Next Steps

- Check the individual README files for each component for more details
- Explore customizing agents for specific tasks
- Review the architecture diagram to understand system communication flow 