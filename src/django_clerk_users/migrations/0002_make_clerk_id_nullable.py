# Generated migration for hybrid authentication support

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("django_clerk_users", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="clerkuser",
            name="clerk_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Unique identifier from Clerk. Can be null for Django admin users.",
                max_length=255,
                null=True,
                unique=True,
            ),
        ),
    ]
