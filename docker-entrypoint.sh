#!/bin/sh
# Prepare the state volume, then start gunicorn.
set -e
mkdir -p "$HDN_STATE_DIR/media"
python manage.py migrate --noinput -v0

# First login account, created once from DJANGO_SUPERUSER_USERNAME/PASSWORD.
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  python manage.py shell -c "
import os
from django.contrib.auth import get_user_model
U = get_user_model(); name = os.environ['DJANGO_SUPERUSER_USERNAME']
if not U.objects.filter(username=name).exists():
    U.objects.create_superuser(name, os.environ.get('DJANGO_SUPERUSER_EMAIL', ''), os.environ['DJANGO_SUPERUSER_PASSWORD'])
    print('created user', name)
"
fi

# One worker: trained models are kept in process memory (see views._models).
# Threads cover concurrency, since requests mostly wait on the endpoints.
exec gunicorn centralproject.wsgi:application \
  --bind 0.0.0.0:8000 --workers 1 --threads 8 --timeout 60 \
  --access-logfile - "$@"
