# centralproject/urls.py
from django.urls import path, include
from catalogapp.views import home
from catalogapp import accounts, network
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('',                 home,                name='home'),
    # HDN network protocols, called by endpoints (no login: requests are signed)
    path('hdn/key/',         network.hdn_key,     name='hdn_key'),
    path('hdn/enroll/',      network.hdn_enroll,  name='hdn_enroll'),
    path('catalog/',         include('catalogapp.urls')),
    # login
    path('login/', accounts.FirstStartLoginView.as_view(), name='login'),
    # first start: the administrator registers here; closed once a user exists
    path('setup/', accounts.setup_view, name='setup'),

    # logout (optional)
    path('logout/',
         auth_views.LogoutView.as_view(next_page='login'),
         name='logout'),
] + static('/media/', document_root=settings.MEDIA_ROOT)  # unprefixed: the proxy strips HDN_URL_PREFIX
    