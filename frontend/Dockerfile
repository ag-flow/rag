# frontend/Dockerfile

# Stage 1 : build Vite
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2 : serve via Nginx
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html/ui
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=10s --retries=5 \
  CMD wget -qO- http://localhost:80/healthz || exit 1
