FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
# NOTE: nginx 公式イメージは master を root, worker は nginx ユーザーで実行する。
# port 80 のバインドに root が必要なため、ここで USER nginx に切替えると
# 起動失敗となる。完全 non-root 化する場合は nginx-unprivileged を採用し
# EXPOSE 8080 / nginx.conf の listen 8080 へ変更すること。
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
