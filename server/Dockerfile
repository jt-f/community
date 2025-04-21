FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy only what's needed for dependency installation first
COPY shared_models /app/shared_models
COPY shared/protos /app/shared/protos
COPY server/pyproject.toml server/poetry.lock* ./

# Install Poetry
RUN pip install poetry==2.1.1

# Tell Poetry not to use a virtual environment
ENV POETRY_VIRTUALENVS_CREATE=false

# Install dependencies including shared_models
RUN pip install -e /app/shared_models && \
    poetry install --no-root

# Now copy the rest of the application
COPY server/ .

# Set Python path
ENV PYTHONPATH=/app:/app/src:/app/generated

# Expose ports
EXPOSE 8765 50051

# Run the application
CMD ["./run.sh"]