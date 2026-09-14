FROM node:22-alpine AS build

WORKDIR /workspace
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && npm ci --legacy-peer-deps

COPY docs/api ./docs/api
COPY frontend ./frontend
RUN cd frontend && npm run api:types && npm run build

FROM nginx:1.27-alpine
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /workspace/frontend/dist/frontend/browser /usr/share/nginx/html

EXPOSE 80
