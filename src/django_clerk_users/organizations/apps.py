from django.apps import AppConfig


class OrganizationsConfig(AppConfig):
    name = "django_clerk_users.organizations"
    label = "clerk_organizations"
    verbose_name = "Clerk Organizations"
    default_auto_field = "django.db.models.BigAutoField"
