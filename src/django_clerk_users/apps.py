from django.apps import AppConfig


class DjangoClerkUsersConfig(AppConfig):
    name = "django_clerk_users"
    verbose_name = "Django Clerk Users"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        # Disconnect Django's update_last_login signal
        # Clerk manages authentication externally
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import update_last_login
        from django.contrib.auth.signals import user_logged_in

        User = get_user_model()
        user_logged_in.disconnect(update_last_login, sender=User)
