FROM golang:1.25-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /snake .

FROM alpine:3.21
RUN adduser -D -u 10001 snake
COPY --from=build /snake /snake

# Flag is read from /flag.txt (overwritten by the platform) or the FLAG env var.
RUN echo 'ctfcup{test_flag}' > /flag.txt && chmod 0444 /flag.txt

USER snake
ENV ADDR=:8080
EXPOSE 8080
ENTRYPOINT ["/snake"]
