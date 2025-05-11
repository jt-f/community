# Stage 1: Builder
FROM python:3.13-slim AS builder

WORKDIR /app

# Install system dependencies required for building packages and poetry
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry (use a stable version)
RUN pip install --no-cache-dir poetry==1.8.2

# Configure Poetry to not create virtual environments within the project
# Packages will be installed into the system Python's site-packages.
ENV POETRY_VIRTUALENVS_CREATE=false \
    POETRY_CACHE_DIR=/root/.cache/pypoetry

# Copy dependency definition files
COPY agent/pyproject.toml agent/poetry.lock* ./
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
COPY agent/src/ src/
COPY agent/run.sh agent/build_protos.sh ./

# Ensure scripts are executable
RUN chmod +x /app/run.sh && chmod +x /app/build_protos.sh

# Stage 2: Final image
FROM python:3.13-slim AS final

WORKDIR /app

# Create a non-root user for security and its home directory
RUN groupadd --system appuser && \
    useradd --system --gid appuser --home-dir /home/appuser --create-home appuser

# Set environment variables for the final stage
ENV POETRY_VIRTUALENVS_CREATE=false \
    HOME=/home/appuser \
    # Add .local/bin to PATH for user-installed executables (if any)
    PATH=/home/appuser/.local/bin:${PATH}

# Copy installed dependencies from the builder stage
COPY --from=builder /usr/local/lib/python3.13/site-packages/ /usr/local/lib/python3.13/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Copy shared models and protos (runtime dependency)
COPY --from=builder /app/shared_models/ /app/shared_models/
COPY --from=builder /app/shared/protos/ /app/shared/protos/

# Copy application code and scripts from the builder stage
COPY --from=builder /app/src/ src/
COPY --from=builder /app/run.sh /app/build_protos.sh ./
COPY --from=builder /app/pyproject.toml /app/poetry.lock* ./

# Set Python path
ENV PYTHONPATH=/app:/app/src:/app/generated

# Ensure scripts are executable (already done in builder, but good for clarity if copied separately)
RUN chmod +x /app/run.sh && chmod +x /app/build_protos.sh

# Switch to non-root user
RUN chown -R appuser:appuser /app && \
    chown -R appuser:appuser /home/appuser # Ensure appuser owns its home directory
USER appuser

# Expose ports (if any, agent usually doesn't expose ports directly)
# EXPOSE XXXXX

# Run the application
CMD ["./run.sh"]