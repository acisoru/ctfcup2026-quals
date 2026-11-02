FROM ubuntu:22.04

# The service is a static-PIE binary (no shared library dependencies).
WORKDIR /app
COPY service /app/service
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod 755 /app/service /app/entrypoint.sh

EXPOSE 1337
ENTRYPOINT ["/app/entrypoint.sh"]
