# Stage 1: generate gzip siblings for the large WASM/PCK/JS payloads.
FROM python:3.12-alpine AS assets

COPY server.py /tmp/server.py
COPY game/ /game/

RUN python /tmp/server.py --precompress /game


# Stage 2: nginx serving the static export over plain HTTP.
# TLS is terminated by the platform in front of the container.
FROM nginxinc/nginx-unprivileged:1.27-alpine

COPY nginx/nginx.conf /etc/nginx/nginx.conf
COPY nginx/burmalda.conf /etc/nginx/conf.d/default.conf
COPY nginx/snippets/game.conf /etc/nginx/snippets/game.conf
COPY --from=assets /game/ /usr/share/nginx/html/

USER nginx

EXPOSE 8080
