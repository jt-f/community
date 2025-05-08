# Stage 1: Build stage
FROM node:23-slim AS builder

WORKDIR /app

# Copy package.json and package-lock.json
COPY frontend/package.json ./
COPY frontend/package-lock.json ./
# If you have other files crucial for dependency installation (e.g., .npmrc), copy them here too.
# COPY frontend/.npmrc ./

# Install dependencies with BuildKit cache mount
# This leverages caching for npm's global cache directory.
RUN --mount=type=cache,id=npm,target=/root/.npm npm ci --prefer-offline --no-audit

# Copy the rest of the frontend application files needed for the build
COPY frontend/tsconfig.json frontend/tsconfig.node.json ./
COPY frontend/src ./src
COPY frontend/public ./public
COPY frontend/index.html ./
COPY frontend/vite.config.ts ./

# Build the application
RUN npm run build

# Stage 2: Production stage
FROM node:23-slim AS production

WORKDIR /app

# Create a non-root user and group for security
RUN groupadd --system appuser && useradd --system --gid appuser appuser

# Copy only the built artifacts from the builder stage
COPY --from=builder --chown=appuser:appuser /app/dist ./dist

# Copy package.json to allow `npx serve` to find project context if needed, though often not strictly necessary for `serve`.
# If `serve` or other runtime tools need specific package.json scripts or dependencies, ensure they are production dependencies.
COPY --from=builder --chown=appuser:appuser /app/package.json /app/package-lock.json* ./

# Set npm cache to a writable directory to avoid permission issues with npx
ENV NPM_CONFIG_CACHE=/tmp/.npm-cache

# Install `serve` globally or ensure it's a production dependency if not already.
# If `serve` is listed in devDependencies, this RUN command would be needed.
# RUN npm install -g serve # Or, if it's a prod dep: npm ci --omit=dev

# Switch to the non-root user
USER appuser

EXPOSE 5173

# Use a more specific command for serve, ensuring it serves from the correct directory
CMD ["npx", "serve", "-s", "dist", "-l", "5173"]
