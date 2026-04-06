# Stage 1: Build Angular app
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies (ci = clean install, uses package-lock.json)
COPY package.json ./
RUN npm install

COPY . .
RUN npm run build -- --configuration production

# Stage 2: Serve with nginx
FROM nginx:1.25-alpine

# Copy the built Angular files
COPY --from=builder /app/dist/frontend/browser /usr/share/nginx/html

# Copy nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
