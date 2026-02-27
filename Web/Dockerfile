# Build Stage
FROM node:25.4.0-alpine3.22 as build

WORKDIR /app

COPY package*.json ./
RUN npm install

ARG VITE_API_TOKEN
ENV VITE_API_TOKEN=$VITE_API_TOKEN

COPY . .
RUN npm run build

# Production Stage
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
