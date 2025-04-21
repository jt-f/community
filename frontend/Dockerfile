FROM node:18-alpine

WORKDIR /app

# Copy package files with explicit paths
COPY ./frontend/package.json ./frontend/package-lock.json ./frontend/tsconfig.json ./

# Install dependencies and update package-lock.json
RUN npm install

# Copy the rest of the application
COPY ./frontend/ .
# Build the application
RUN npm run build

# Install serve to run the production build
RUN npm install -g serve

# Expose port
EXPOSE 5173

# Run the application
CMD ["serve", "-s", "dist", "-l", "5173"] 