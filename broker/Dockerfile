FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy only what's needed for dependency installation first
COPY shared_models /app/shared_models
COPY broker/pyproject.toml broker/poetry.lock* ./

# Install Poetry
RUN pip install poetry==1.7.1

# Tell Poetry not to use a virtual environment
ENV POETRY_VIRTUALENVS_CREATE=false

# Install dependencies including shared_models
RUN pip install -e /app/shared_models && \
    poetry install --no-root

# Now copy the rest of the application
COPY broker/ .

# Create necessary directories and files
RUN mkdir -p src/protos generated src/generated && \
    touch src/generated/__init__.py generated/__init__.py

# Generate gRPC code
RUN python generate_grpc.py

# Set Python path
ENV PYTHONPATH=/app:/app/src:/app/generated

# Run the application
CMD ["python", "src/broker.py"] 