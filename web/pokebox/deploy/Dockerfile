FROM ruby:3.3-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libsqlite3-dev libyaml-dev \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --system --create-home --shell /usr/sbin/nologin app

WORKDIR /app

COPY Gemfile /app/Gemfile
RUN bundle install

COPY app/     /app/app/
COPY views/   /app/views/
COPY public/  /app/public/
COPY config.ru /app/config.ru
COPY entrypoint.sh /entrypoint.sh

RUN chown -R root:root /app /entrypoint.sh \
    && chmod -R 0555 /app \
    && chmod 0555 /entrypoint.sh \
    && mkdir -p /data && chown app:app /data

ENV RACK_ENV=production

# flag placed here by the platform; overwritten at deploy. See entrypoint.sh.
RUN echo 'ctfcup{test_flag}' > /flag.txt

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
