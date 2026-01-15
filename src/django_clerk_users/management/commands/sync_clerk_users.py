"""
Management command to sync users from Clerk to Django.
"""

from django.core.management.base import BaseCommand, CommandError

from django_clerk_users.client import get_clerk_client
from django_clerk_users.exceptions import ClerkConfigurationError
from django_clerk_users.utils import update_or_create_clerk_user


class Command(BaseCommand):
    help = "Sync users from Clerk to Django database"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Maximum number of users to sync per batch (default: 100)",
        )
        parser.add_argument(
            "--offset",
            type=int,
            default=0,
            help="Offset to start syncing from (default: 0)",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Sync all users (paginate through all results)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be synced without making changes",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        offset = options["offset"]
        sync_all = options["all"]
        dry_run = options["dry_run"]

        try:
            clerk = get_clerk_client()
        except ClerkConfigurationError:
            raise CommandError(
                "CLERK_SECRET_KEY is not configured. "
                "Set it in your Django settings to use Clerk sync commands."
            )

        created_count = 0
        updated_count = 0
        error_count = 0
        total_count = 0

        self.stdout.write("Starting user sync from Clerk...")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes will be made"))

        while True:
            self.stdout.write(f"Fetching users (offset={offset}, limit={limit})...")

            try:
                response = clerk.users.list(limit=limit, offset=offset)
                users = response.data if hasattr(response, "data") else response
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Failed to fetch users: {e}"))
                break

            if not users:
                self.stdout.write("No more users to sync.")
                break

            for clerk_user in users:
                total_count += 1
                clerk_id = getattr(clerk_user, "id", None)

                if not clerk_id:
                    error_count += 1
                    continue

                email = None
                email_addresses = getattr(clerk_user, "email_addresses", []) or []
                if email_addresses:
                    email = getattr(email_addresses[0], "email_address", None)

                if dry_run:
                    self.stdout.write(f"  Would sync: {email} ({clerk_id})")
                    continue

                try:
                    user, created = update_or_create_clerk_user(clerk_id)
                    if created:
                        created_count += 1
                        self.stdout.write(
                            self.style.SUCCESS(f"  Created: {user.email}")
                        )
                    else:
                        updated_count += 1
                        self.stdout.write(f"  Updated: {user.email}")
                except Exception as e:
                    error_count += 1
                    self.stderr.write(
                        self.style.ERROR(f"  Failed to sync {clerk_id}: {e}")
                    )

            if not sync_all:
                break

            offset += limit

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Sync complete!"))
        self.stdout.write(f"  Total processed: {total_count}")
        if not dry_run:
            self.stdout.write(f"  Created: {created_count}")
            self.stdout.write(f"  Updated: {updated_count}")
        self.stdout.write(f"  Errors: {error_count}")
