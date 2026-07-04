# Stage 1: Build the React application
FROM oven/bun:1-alpine AS builder

WORKDIR /app

# Copy entire workspace (Bun workspaces require all packages for lockfile resolution)
COPY . .

# Install dependencies from workspace root (resolves workspace deps)
RUN bun install

# Build the frontend application from workspace root
WORKDIR /app/frontend
RUN bun run build

# Stage 2: Serve with nginx
FROM nginx:alpine

# Copy built files from builder stage
COPY --from=builder /app/frontend/dist /usr/share/nginx/html

# Copy nginx configuration
COPY --from=builder /app/frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]