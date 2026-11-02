FROM golang:1.24-alpine AS init
COPY docus-init/ /src/
WORKDIR /src
RUN CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o /out/docus-init . \
	&& CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o /out/patch-forkit ./patch

FROM alpine AS flag
RUN echo "flag{example}" > /flag.txt

FROM collabora/code:26.04.3.2.1

COPY --from=flag /flag.txt /flag.txt

COPY coolwsd.xml /etc/coolwsd/coolwsd.xml
COPY coolwsd.xml /opt/cool/systemplate/etc/coolwsd/coolwsd.xml
COPY --from=init /out/docus-init /usr/local/bin/docus-init

COPY --from=init /out/patch-forkit /tmp/patch-forkit
USER 0
RUN ["/tmp/patch-forkit", "/usr/bin/coolforkit-caps"]
USER 1001

ENTRYPOINT ["/usr/local/bin/docus-init"]
