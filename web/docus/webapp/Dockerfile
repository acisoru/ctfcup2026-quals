FROM golang:1.24-alpine AS build
COPY go.mod main.go auth.go docs.go templates.go /src/
WORKDIR /src
RUN CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o /out/webapp .

FROM alpine:3.20
COPY --from=build /out/webapp /usr/local/bin/webapp
ENTRYPOINT ["/usr/local/bin/webapp"]
