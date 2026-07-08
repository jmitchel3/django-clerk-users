"""
Management command to migrate existing Django users to Clerk.

This command creates users in Clerk from your existing Django user database,
allowing you to migrate to Clerk authentication without losing user data.

Note: Passwords cannot be migrated. Users will need to reset their password
or use OAuth/social login.
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from django.apps import apps
from django.conf import settings
from django.core.exceptions import FieldDoesNotExist
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from django_clerk_users.client import get_clerk_client
from django_clerk_users.exceptions import ClerkConfigurationError
from django_clerk_users.server_api import (
    _duplicate_error_params,
    _has_duplicate_identifier_error,
)
from django_clerk_users.utils import _clerk_list_data, _clerk_timeout_options


class Command(BaseCommand):
    help = "Migrate existing Django users to Clerk"

    def add_arguments(self, parser):
        parser.add_argument(
            "--source-model",
            type=str,
            default="auth.User",
            help="Source user model in app.Model format (default: auth.User)",
        )
        parser.add_argument(
            "--email",
            type=str,
            help="Migrate a specific user by email address",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Migrate all users",
        )
        parser.add_argument(
            "--created-before",
            type=str,
            help="Migrate users created before this date (YYYY-MM-DD)",
        )
        parser.add_argument(
            "--skip-existing",
            action="store_true",
            help="Skip users that already exist in Clerk (by email)",
        )
        parser.add_argument(
            "--skip-password-email",
            action="store_true",
            default=True,
            help=(
                "Compatibility flag; migrated users are created passwordless and "
                "no password email is sent."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be migrated without making changes",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Limit number of users to migrate (default: 100)",
        )

    def handle(self, *args, **options):
        # Get the source model
        source_model_path = options["source_model"]
        try:
            app_label, model_name = source_model_path.split(".")
            SourceUser = apps.get_model(app_label, model_name)
        except (ValueError, LookupError) as e:
            raise CommandError(f"Invalid source model '{source_model_path}': {e}")

        email = options["email"]
        migrate_all = options["all"]
        created_before = options["created_before"]
        skip_existing = options["skip_existing"]
        dry_run = options["dry_run"]
        limit = options["limit"]

        if limit <= 0:
            raise CommandError("--limit must be greater than zero")

        if not email and not migrate_all and not created_before:
            raise CommandError("You must specify --email, --all, or --created-before")

        try:
            clerk = get_clerk_client()
        except ClerkConfigurationError:
            raise CommandError(
                "CLERK_SECRET_KEY is not configured. "
                "Set it in your Django settings to use Clerk sync commands."
            )

        # Build queryset
        queryset = SourceUser.objects.all()

        if email:
            queryset = queryset.filter(email=email)
        elif created_before:
            before_date = self._parse_created_before(created_before)
            created_field = self._created_before_field(SourceUser)
            queryset = queryset.filter(**{f"{created_field}__lt": before_date})

        queryset = queryset[:limit]

        created_count = 0
        skipped_count = 0
        error_count = 0
        linked_count = 0
        total_count = 0

        self.stdout.write(f"Migrating users from {source_model_path}...")
        self.stdout.write(f"Found {queryset.count()} users to process")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes will be made"))

        for source_user in queryset:
            total_count += 1
            user_email = getattr(source_user, "email", None)

            if not user_email:
                self.stderr.write(
                    self.style.WARNING(f"  Skipping user {source_user.pk}: no email")
                )
                skipped_count += 1
                continue

            first_name = getattr(source_user, "first_name", "") or ""
            last_name = getattr(source_user, "last_name", "") or ""

            # Check if user exists in Clerk
            if skip_existing:
                try:
                    users_data = self._find_existing_clerk_users(clerk, user_email)
                    if users_data:
                        if dry_run:
                            self.stdout.write(
                                f"  Would skip (exists in Clerk): {user_email}"
                            )
                        else:
                            self.stdout.write(
                                f"  Skipping (exists in Clerk): {user_email}"
                            )
                            # Try to link the user
                            clerk_user = users_data[0]
                            self._link_user(source_user, clerk_user)
                            linked_count += 1
                        skipped_count += 1
                        continue
                except Exception as e:
                    error_count += 1
                    self.stderr.write(
                        self.style.WARNING(
                            f"  Error checking if {user_email} exists: {e}"
                        )
                    )
                    continue

            if dry_run:
                self.stdout.write(f"  Would create: {user_email}")
                continue

            # Create user in Clerk
            try:
                clerk_user = clerk.users.create(
                    email_address=[user_email],
                    first_name=first_name if first_name else None,
                    last_name=last_name if last_name else None,
                    skip_password_requirement=True,
                    skip_password_checks=True,
                    **_clerk_timeout_options(),
                )

                # Link Django user to Clerk
                self._link_user(source_user, clerk_user)

                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"  Created: {user_email}"))

            except Exception as e:
                if self._is_duplicate_email_error(e):
                    self.stdout.write(
                        self.style.WARNING(
                            f"  Email already exists in Clerk: {user_email}"
                        )
                    )
                    try:
                        users_data = self._find_existing_clerk_users(clerk, user_email)
                    except Exception as lookup_error:
                        error_count += 1
                        self.stderr.write(
                            self.style.WARNING(
                                "  Error linking existing Clerk user for "
                                f"{user_email}: {lookup_error}"
                            )
                        )
                    else:
                        if users_data:
                            self._link_user(source_user, users_data[0])
                            linked_count += 1
                    skipped_count += 1
                else:
                    error_count += 1
                    self.stderr.write(
                        self.style.ERROR(f"  Failed to create {user_email}: {e}")
                    )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Migration complete!"))
        self.stdout.write(f"  Total processed: {total_count}")
        if not dry_run:
            self.stdout.write(f"  Created in Clerk: {created_count}")
            self.stdout.write(f"  Linked existing: {linked_count}")
        self.stdout.write(f"  Skipped: {skipped_count}")
        self.stdout.write(f"  Errors: {error_count}")

        if not dry_run and created_count > 0:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    "Note: Migrated users will need to reset their password "
                    "or use OAuth to sign in."
                )
            )

    def _find_existing_clerk_users(self, clerk, user_email: str) -> list[Any]:
        existing_users = clerk.users.list(
            request={"email_address": [user_email], "limit": 1},
            **_clerk_timeout_options(),
        )
        return _clerk_list_data(existing_users)

    @staticmethod
    def _parse_created_before(raw_value: str) -> datetime:
        try:
            before_date = datetime.strptime(raw_value, "%Y-%m-%d")
        except ValueError:
            raise CommandError("Invalid date format. Use YYYY-MM-DD")

        if settings.USE_TZ and timezone.is_naive(before_date):
            return timezone.make_aware(before_date, timezone.get_current_timezone())
        return before_date

    @staticmethod
    def _created_before_field(source_model) -> str:
        for field_name in ("date_joined", "created_at"):
            try:
                source_model._meta.get_field(field_name)
            except FieldDoesNotExist:
                continue
            return field_name
        raise CommandError(
            "Source model must define date_joined or created_at to use --created-before"
        )

    @staticmethod
    def _get_clerk_value(clerk_user, key: str):
        if isinstance(clerk_user, Mapping):
            return clerk_user.get(key)
        return getattr(clerk_user, key, None)

    @staticmethod
    def _is_duplicate_email_error(exc: Exception) -> bool:
        if _has_duplicate_identifier_error(exc):
            params = _duplicate_error_params(exc)
            return "email_address" in params or not params

        error_str = str(exc).lower()
        return "email_address" in error_str and (
            "taken" in error_str or "exists" in error_str or "not unique" in error_str
        )

    def _link_user(self, source_user, clerk_user):
        """
        Link a Django user to their Clerk user.

        If the source user has a clerk_id field, update it.
        """
        clerk_id = self._get_clerk_value(clerk_user, "id")
        if not clerk_id:
            return

        # Check if source user has clerk_id field
        if hasattr(source_user, "clerk_id"):
            source_user.clerk_id = clerk_id
            source_user.save(update_fields=["clerk_id"])
            self.stdout.write(f"    Linked clerk_id: {clerk_id}")
