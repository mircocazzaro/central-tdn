# centralproject/urls.py
from django.urls import path, include
from catalogapp.views import home
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('',                 home,                name='home'),
    path('catalog/',         include('catalogapp.urls')),
    # login
    path('login/',
         auth_views.LoginView.as_view(
             template_name='catalogapp/login.html'
         ),
         name='login'),

    # logout (optional)
    path('logout/',
         auth_views.LogoutView.as_view(next_page='login'),
         name='logout'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    