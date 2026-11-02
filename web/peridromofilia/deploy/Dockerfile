FROM python:3.12-slim

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py models.py seed.py stations.py catalog.json ./
COPY templates/ ./templates/

EXPOSE 8080
CMD ["sh", "-c", "python seed.py && gunicorn --bind 0.0.0.0:8080 --workers 2 --preload main:app"]
