FROM node:20-slim

WORKDIR /app

# Install dependencies first (better caching)
COPY ./frontend/package*.json ./
COPY ./frontend/tsconfig.json ./
COPY ./frontend/tsconfig.node.json ./

# Use npm cache mount and install dependencies
RUN --mount=type=cache,target=/root/.npm npm ci

# Copy only the necessary source files
COPY ./frontend/src ./src
COPY ./frontend/public ./public
COPY ./frontend/index.html ./
COPY ./frontend/vite.config.ts ./

# Build the application
RUN npm run build

EXPOSE 5173

CMD ["npx", "serve", "-s", "dist", "-l", "5173"]
