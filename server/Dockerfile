# Stage 1: Builder
FROM python:3.13-slim AS builder

WORKDIR /app

# Install system dependencies required for building packages, curl (for healthchecks), and poetry
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry (use a stable version)
RUN pip install --no-cache-dir poetry==1.8.2

# Configure Poetry
ENV POETRY_VIRTUALENVS_CREATE=false \
    POETRY_CACHE_DIR=/root/.cache/pypoetry

# Copy dependency definition files
COPY server/pyproject.toml server/poetry.lock* ./
# Copy shared models and protos as they are local dependencies
COPY shared_models/ /app/shared_models/
COPY shared/protos/ /app/shared/protos/

# Install dependencies using Poetry with BuildKit cache mounts
# This installs shared_models in editable mode and then project dependencies
RUN \
    --mount=type=cache,target=/root/.cache/pip \
    --mount=type=cache,target=${POETRY_CACHE_DIR} \
    sh -c "pip install --no-cache-dir -e /app/shared_models && poetry install --no-root --no-dev"

# Copy application source code and scripts
COPY server/src/ src/
COPY server/run.sh server/build_protos.sh ./

# Ensure scripts are executable
RUN chmod +x /app/run.sh && chmod +x /app/build_protos.sh

# Stage 2: Final image
FROM python:3.13-slim AS final

WORKDIR /app

# Install curl in the final stage for health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user for security
RUN groupadd --system appuser && useradd --system --gid appuser appuser

# Create and set permissions for the log directory BEFORE switching user
# This ensures the directory exists and is writable by appuser,
# especially important when a volume is mounted to /var/log.
RUN mkdir -p /var/log && chown appuser:appuser /var/log

# Copy installed dependencies from the builder stage
COPY --from=builder /usr/local/lib/python3.13/site-packages/ /usr/local/lib/python3.13/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Copy shared models and protos (runtime dependency)
COPY --from=builder /app/shared_models/ /app/shared_models/
COPY --from=builder /app/shared/protos/ /app/shared/protos/

# Copy application code and scripts from the builder stage
COPY --from=builder /app/src/ src/
COPY --from=builder /app/run.sh /app/build_protos.sh ./

# Set Python path
ENV PYTHONPATH=/app:/app/src:/app/generated

# Ensure scripts are executable
RUN chmod +x /app/run.sh && chmod +x /app/build_protos.sh

# Switch to non-root user
USER appuser

# Expose ports
EXPOSE 8765 50051

# Run the application
CMD ["./run.sh"]