from django.urls import path
from . import compose_views, views

urlpatterns = [
    path('',              views.central_catalog,      name='central_catalog'),
    path('query/',     views.query_view,   name='central_query'),
    # user queries answered by rewriting over the catalog
    path('compose/',             compose_views.compose_page,       name='compose'),
    path('compose/vocabulary/',  compose_views.compose_vocabulary, name='compose_vocabulary'),
    path('compose/plan/',        compose_views.compose_plan,       name='compose_plan'),
    path('compose/run/',         compose_views.compose_run,        name='compose_run'),
    # endpoint manager
    path('manager/',            views.endpoint_manager, name='endpoint_manager'),
    path('manager/add/',        views.endpoint_add,     name='endpoint_add'),
    path('manager/<int:pk>/edit/',   views.endpoint_edit,    name='endpoint_edit'),
    path('manager/<int:pk>/delete/', views.endpoint_delete,  name='endpoint_delete'),
    path('manager/applications/<int:pk>/', views.enrollment_decide, name='enrollment_decide'),
    path('manager/publish-catalog/', views.publish_catalog, name='publish_catalog'),
    path('manager/publish-ontology/', views.publish_ontology, name='publish_ontology'),
    path('run_analytics/', views.run_analytics, name='run_analytics'),
    path('train-model/', views.train_model, name='train_model'),
    path('predict-model/', views.predict_model, name='predict_model'),
]
