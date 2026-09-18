FROM python:3.12-slim

# Runs as a non-root user; /data is the only writable path it needs.
RUN useradd --system --uid 10001 --create-home --shell /usr/sbin/nologin imagery

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server/ ./server/
COPY static/ ./static/
COPY wsgi.py .

RUN mkdir -p /data && chown -R imagery:imagery /data /app
USER imagery

ENV IMAGERY_DB=/data/imagery.db \
    IMAGERY_UPLOADS=/data/uploads \
    IMAGERY_SECRET_FILE=/data/secret_key \
    PYTHONUNBUFFERED=1

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=3).status==200 else 1)"

# 2 workers is plenty for a personal gallery; threads help with media streaming.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", \
     "--timeout", "60", "--access-logfile", "-", "wsgi:app"]
