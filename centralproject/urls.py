# centralproject/urls.py
from django.urls import path, include
from catalogapp.views import home
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('',                 home,                name='home'),
    path('catalog/',         include('catalogapp.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    