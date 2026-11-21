from django.urls import path

from . import views

app_name = "productdle"

urlpatterns = [
    path("", views.index, name="index"),
    path("statistics/", views.statistics, name="statistics"),
    path("healthz", views.healthz, name="healthz"),
    path("search/", views.search, name="search"),
    path("guess/", views.guess, name="guess"),
    path("reveal/", views.reveal, name="reveal"),
]
