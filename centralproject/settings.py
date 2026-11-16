import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('-dzyj5_ndx2xn7#4-mvxbuxc^2g!=pelj!0l7s$-emri3cog^$', 'unsafe-dev-key')
#DEBUG = os.getenv('DEBUG', 'False') == 'True'
DEBUG = True
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.staticfiles',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'catalogapp',
]

MIDDLEWARE = [
    'catalogapp.middleware.CollapseSlashesMiddleware',            # Apache ProxyPass sends //path
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',                 # static files under gunicorn
    'django.contrib.sessions.middleware.SessionMiddleware',       # ← fixed
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',                  # if you need CSRF
    'django.contrib.auth.middleware.AuthenticationMiddleware',    # for auth
    'django.contrib.messages.middleware.MessageMiddleware',
]

ROOT_URLCONF = 'centralproject.urls'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / 'catalogapp' / 'templates'],
    'APP_DIRS': True,
    'OPTIONS': {
        'context_processors': [
            'django.template.context_processors.request',
            'django.contrib.auth.context_processors.auth',
            'django.contrib.messages.context_processors.messages',
        ],
    },
}]



# Keep the existing integer ids (no migration needed)
DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

WSGI_APPLICATION = 'centralproject.wsgi.application'

# Public path prefix when Central is served under a reverse proxy path, e.g.
# HDN_URL_PREFIX=/api0 for http://host/api0/. Empty (the default) keeps the
# root-level URLs used locally and in the Docker container.
URL_PREFIX = os.getenv('HDN_URL_PREFIX', '').rstrip('/')
FORCE_SCRIPT_NAME = URL_PREFIX or None

STATIC_URL = f'{URL_PREFIX}/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
# WhiteNoise matches the path the WSGI server passes in, which the proxy has
# already stripped of the prefix, so it must keep the unprefixed path.
WHITENOISE_STATIC_PREFIX = '/static/'


# State lives under HDN_STATE_DIR when set (the Docker image mounts a volume
# there); otherwise in the project directory, as before.
STATE_DIR = Path(os.getenv('HDN_STATE_DIR', BASE_DIR))

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': STATE_DIR / 'db.sqlite3',
    }
}

# Origins allowed to POST (login, forms) when the site is reached through a
# proxy: comma-separated, e.g. http://tdn.dei.unipd.it
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.getenv('HDN_CSRF_TRUSTED_ORIGINS', '').split(',') if o.strip()]

MEDIA_URL = f'{URL_PREFIX}/media/'
MEDIA_ROOT = STATE_DIR / 'media'

# Simple manager password (in real life use env var!)
ENDPOINT_MANAGER_PASSWORD = 'supersecret'

# Name shown to endpoints that apply to this Central
HDN_CENTRAL_NAME = os.getenv('HDN_CENTRAL_NAME', 'HDN Central')


# Redirect here after a successful login
LOGIN_REDIRECT_URL = f'{URL_PREFIX}/catalog/'
# If someone hits @login_required they go here
LOGIN_URL = f'{URL_PREFIX}/login/'

# Make sessions expire after, say, 1 hour (3600s)
SESSION_COOKIE_AGE = 3600        # seconds
# (Optional) refresh expiry on every request
SESSION_SAVE_EVERY_REQUEST = True
