# Getting Started Guide

This guide covers the initial setup required to run the Agent Communication System, focusing on prerequisites and core infrastructure.

For an overview of the system architecture and links to run individual components (Server, Broker, Agent, Frontend), please refer to the main [Project README](./README.md).

## Prerequisites

Ensure the following are installed on your system:

1.  **Docker and Docker Compose V2:** Required for running the core infrastructure (e.g., RabbitMQ).
    *   **Windows/Mac:** Install [Docker Desktop](https://www.docker.com/products/docker-desktop).
    *   **Linux:** Follow the official Docker Engine and Docker Compose plugin installation guides for your distribution (e.g., [Ubuntu guide](https://docs.docker.com/engine/install/ubuntu/)).

2.  **Python (3.13.2+):** Required for running the backend services (Server, Broker, Agent).
    *   Using a version manager like [pyenv](https://github.com/pyenv/pyenv) is recommended:
        ```bash
        pyenv install 3.13.2
        pyenv global 3.13.2
        ```

3.  **Poetry:** Python dependency management tool.
    ```bash
    curl -sSL https://install.python-poetry.org | python3 -
    # Or follow official installation instructions
    ```

4.  **Node.js (v18+) and npm/yarn:** Required for the Frontend service.
    *   Install from [nodejs.org](https://nodejs.org/) or use a version manager like [nvm](https://github.com/nvm-sh/nvm).

5.  **Git:** For cloning the repository.

## Initial Project Setup

1.  **Clone the Repository:**
    ```bash
    git clone <repository-url> # Replace with your repository URL
    cd community
    ```

2.  **Start Core Infrastructure (RabbitMQ):**
    Use Docker Compose to start the RabbitMQ message broker.
    ```bash
    docker compose up --build -d rabbitmq
    # (Ensure 'rabbitmq' service is defined in your docker-compose.yml)
    ```
    You can check the status with `docker compose ps`.

## Next Steps

With the prerequisites installed and RabbitMQ running, you can now set up and run the individual components:

*   **[Server](./server/README.md)**
*   **[Broker](./broker/README.md)**
*   **[Agent](./agent/README.md)**
*   **[Frontend](./frontend/README.md)**

Follow the instructions in each component's README file for specific installation (dependency installation, gRPC code generation) and running steps.