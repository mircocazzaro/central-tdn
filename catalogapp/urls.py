from django.urls import path
from . import views

urlpatterns = [
    path('',              views.central_catalog,      name='central_catalog'),
    path('query/',     views.query_view,   name='central_query'),
    # endpoint manager
    path('manager/',            views.endpoint_manager, name='endpoint_manager'),
    path('manager/add/',        views.endpoint_add,     name='endpoint_add'),
    path('manager/<int:pk>/edit/',   views.endpoint_edit,    name='endpoint_edit'),
    path('manager/<int:pk>/delete/', views.endpoint_delete,  name='endpoint_delete'),
]
