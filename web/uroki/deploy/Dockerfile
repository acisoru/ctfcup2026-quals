FROM python:3.12-slim

RUN useradd --system --create-home --shell /usr/sbin/nologin app

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir "setuptools<81" -r /app/requirements.txt

COPY app/ /app/app/
COPY templates/ /app/templates/
COPY static/ /app/static/
COPY supervisord.conf /etc/supervisord.conf
COPY entrypoint.sh /entrypoint.sh

RUN chown -R root:root /app /etc/supervisord.conf /entrypoint.sh \
    && chmod -R 0555 /app \
    && chmod 0555 /entrypoint.sh \
    && chmod 0444 /etc/supervisord.conf \
    && mkdir -p /data /data/mq /data/uploads \
    && chown -R app:app /data

ENV PYTHONPATH=/app \
    PYTHONSAFEPATH=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN echo 'ctfcup{test_flag}' > /flag.txt

EXPOSE 5000

ENTRYPOINT ["/entrypoint.sh"]
