import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path):
    """Read KEY=VALUE lines of an untracked .env into the environment.

    Variables already set in the environment win. Blank lines and # comments
    are ignored; values may be quoted.
    """
    try:
        lines = open(path, encoding='utf-8').read().splitlines()
    except FileNotFoundError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


_load_dotenv(os.environ.get('HDN_ENV_FILE', BASE_DIR / '.env'))


def _secret_key(state_dir):
    """HDN_SECRET_KEY, or a random key generated once and kept (0600) in the state dir."""
    value = os.environ.get('HDN_SECRET_KEY', '').strip()
    if value:
        return value
    import secrets
    import time
    os.makedirs(state_dir, exist_ok=True)
    path = os.path.join(state_dir, 'secret_key')
    for _ in range(50):
        try:
            with open(path, encoding='utf-8') as fh:
                value = fh.read().strip()
            if value:
                return value
        except FileNotFoundError:
            candidate = secrets.token_urlsafe(64)
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                pass  # another worker is writing it
            else:
                with os.fdopen(fd, 'w', encoding='utf-8') as fh:
                    fh.write(candidate)
                return candidate
        time.sleep(0.05)
    raise RuntimeError('SECRET_KEY unavailable: set HDN_SECRET_KEY')


# State lives under HDN_STATE_DIR when set (the Docker image mounts a volume
# there); otherwise in the project directory, as before.
STATE_DIR = Path(os.getenv('HDN_STATE_DIR', BASE_DIR))

SECRET_KEY = _secret_key(STATE_DIR)
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

# Password of the endpoint manager pages. Never in the code: set
# HDN_MANAGER_PASSWORD in the environment or in the untracked .env. When it is
# empty the manager pages stay closed (see views.require_manager_password).
ENDPOINT_MANAGER_PASSWORD = os.getenv('HDN_MANAGER_PASSWORD', '')

# The first administrator registers on first start (/setup/); passwords are checked.
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 10}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

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
