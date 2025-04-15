FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy only what's needed for dependency installation first
COPY shared_models /app/shared_models
COPY server/pyproject.toml server/poetry.lock* ./

# Install Poetry
RUN pip install poetry==1.7.1

# Tell Poetry not to use a virtual environment
ENV POETRY_VIRTUALENVS_CREATE=false

# Install dependencies including shared_models
RUN pip install -e /app/shared_models && \
    poetry install --no-root

# Now copy the rest of the application
COPY server/ .

# Create necessary directories and files
RUN mkdir -p src/generated generated && \
    touch src/generated/__init__.py generated/__init__.py

# Generate gRPC code
RUN python -m grpc_tools.protoc -I./src/protos --python_out=./src/generated --pyi_out=./src/generated --grpc_python_out=./src/generated ./src/protos/*.proto

# Set Python path
ENV PYTHONPATH=/app:/app/src:/app/src/generated:/app/generated

# Expose ports
EXPOSE 8765 50051

# Run the application
CMD ["python", "src/main.py"]