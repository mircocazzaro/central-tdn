import os
from django.core.wsgi import get_wsgi_application

# 1. Tell Django which settings module to use
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'centralproject.settings')

# 2. Create the WSGI application callable
application = get_wsgi_application()
