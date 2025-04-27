FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry before copying source files for better cache usage
RUN pip install poetry==2.1.1

# Copy only what's needed for dependency installation first
COPY broker/pyproject.toml broker/poetry.lock* ./
COPY shared_models/ /app/shared_models/
COPY shared/protos/ /app/shared/protos/

# Tell Poetry not to use a virtual environment
ENV POETRY_VIRTUALENVS_CREATE=false

# Install dependencies including shared_models
RUN pip install --no-cache-dir -e /app/shared_models && \
    poetry install --no-root

# Now copy the rest of the application
COPY broker/ .

# Set Python path
ENV PYTHONPATH=/app:/app/src:/app/generated

# Run the application
CMD ["./run.sh"]