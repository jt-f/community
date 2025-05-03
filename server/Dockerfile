FROM python:3.13-slim

WORKDIR /app

# Install system dependencies and clean up in one layer
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir poetry==2.1.1

# Tell Poetry not to use a virtual environment
ENV POETRY_VIRTUALENVS_CREATE=false

# Copy only dependency files first for better caching
COPY server/pyproject.toml server/poetry.lock* ./
COPY shared_models/ /app/shared_models/
COPY shared/protos/ /app/shared/protos/

# Install dependencies including shared_models
RUN pip install --no-cache-dir -e /app/shared_models \
    && poetry install --no-root

# Copy only the necessary source files
COPY server/src/ src/
COPY server/run.sh server/build_protos.sh ./


# Set Python path
ENV PYTHONPATH=/app:/app/src:/app/generated

# Expose ports
EXPOSE 8765 50051

# Run the application
CMD ["./run.sh"]