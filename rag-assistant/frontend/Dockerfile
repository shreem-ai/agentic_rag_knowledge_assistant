FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files and install dependencies
COPY package.json package-lock.json ./
RUN npm ci

# Copy source and build
COPY . .
RUN npm run build -- --configuration production

# ── Production image using nginx ─────────────────────────────────────────────
FROM nginx:alpine

# Copy Angular build output
COPY --from=builder /app/dist/frontend/browser /usr/share/nginx/html

# Custom nginx config to handle Angular routing and proxy to backend
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
