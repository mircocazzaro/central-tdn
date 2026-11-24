#!/bin/sh
# Prepare the state volume, then start gunicorn.
set -e
mkdir -p "$HDN_STATE_DIR/media"
python manage.py migrate --noinput -v0

# No account is created here: the administrator registers at /setup/ on first start.

# One worker: trained models are kept in process memory (see views._models).
# Threads cover concurrency, since requests mostly wait on the endpoints.
exec gunicorn centralproject.wsgi:application \
  --bind 0.0.0.0:8000 --workers 1 --threads 8 --timeout 300 \
  --access-logfile - "$@"
