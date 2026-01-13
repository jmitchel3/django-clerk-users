"""
URL configuration for backend project.
"""

from django.contrib import admin
from django.urls import include, path

from django_clerk_users.webhooks import clerk_webhook_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
    path("webhooks/clerk/", clerk_webhook_view, name="clerk_webhook"),
]
