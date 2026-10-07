# HDN Central (Django + gunicorn, port 8000).
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HDN_STATE_DIR=/app/state
# Unprivileged user: Central does not run as root.
RUN useradd --create-home --uid 10001 hdn
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --only-binary=:all: -r requirements.txt
COPY --chown=hdn:hdn . .
RUN chmod +x docker-entrypoint.sh
USER hdn
RUN python manage.py collectstatic --noinput -v0 && mkdir -p state/media
# Database and uploaded logos survive container re-creation.
VOLUME ["/app/state"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/login/', timeout=4).status == 200 else 1)"
ENTRYPOINT ["./docker-entrypoint.sh"]
