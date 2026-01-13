"""
API URL configuration.
"""

from django.urls import path

from . import views

urlpatterns = [
    path("public/", views.public_view, name="public"),
    path("protected/", views.protected_view, name="protected"),
    path("profile/", views.user_profile_view, name="profile"),
]
