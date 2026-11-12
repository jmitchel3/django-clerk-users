from django.apps import AppConfig


class LegacyAppConfig(AppConfig):
    name = "tests.vendored_upgrade.legacy_app"
    label = "legacy_app"
    default_auto_field = "django.db.models.AutoField"
