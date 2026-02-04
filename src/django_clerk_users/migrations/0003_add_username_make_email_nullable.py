"""
Migration to add username field and make email nullable.

This supports Clerk users who authenticate via:
- Username only
- Email only
- Both username and email
- Neither (e.g., phone-only, OAuth-only)

clerk_id is the only required identifier.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("django_clerk_users", "0002_make_clerk_id_nullable"),
    ]

    operations = [
        migrations.AddField(
            model_name="clerkuser",
            name="username",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="User's username from Clerk (optional).",
                max_length=150,
                null=True,
                unique=True,
            ),
        ),
        migrations.AlterField(
            model_name="clerkuser",
            name="email",
            field=models.EmailField(
                blank=True,
                db_index=True,
                help_text="User's email address. May be null for username-only Clerk users.",
                max_length=254,
                null=True,
                unique=True,
            ),
        ),
    ]
