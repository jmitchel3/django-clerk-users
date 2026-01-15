"""
Management command to sync organizations from Clerk to Django.
"""

from django.core.management.base import BaseCommand, CommandError

from django_clerk_users.client import get_clerk_client
from django_clerk_users.exceptions import ClerkConfigurationError


class Command(BaseCommand):
    help = "Sync organizations from Clerk to Django database"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Maximum number of organizations to sync per batch (default: 100)",
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
            help="Sync all organizations (paginate through all results)",
        )
        parser.add_argument(
            "--sync-members",
            action="store_true",
            help="Also sync organization members",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be synced without making changes",
        )

    def handle(self, *args, **options):
        # Check if organizations app is installed
        try:
            from django_clerk_users.organizations.models import Organization
            from django_clerk_users.organizations.webhooks import (
                update_or_create_organization,
            )
        except ImportError:
            self.stderr.write(
                self.style.ERROR(
                    "Organizations app is not installed. "
                    "Add 'django_clerk_users.organizations' to INSTALLED_APPS."
                )
            )
            return

        limit = options["limit"]
        offset = options["offset"]
        sync_all = options["all"]
        sync_members = options["sync_members"]
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

        self.stdout.write("Starting organization sync from Clerk...")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes will be made"))

        while True:
            self.stdout.write(
                f"Fetching organizations (offset={offset}, limit={limit})..."
            )

            try:
                response = clerk.organizations.list(limit=limit, offset=offset)
                orgs = response.data if hasattr(response, "data") else response
            except Exception as e:
                self.stderr.write(
                    self.style.ERROR(f"Failed to fetch organizations: {e}")
                )
                break

            if not orgs:
                self.stdout.write("No more organizations to sync.")
                break

            for clerk_org in orgs:
                total_count += 1
                org_id = getattr(clerk_org, "id", None)
                name = getattr(clerk_org, "name", "Unknown")

                if not org_id:
                    error_count += 1
                    continue

                if dry_run:
                    self.stdout.write(f"  Would sync: {name} ({org_id})")
                    continue

                try:
                    organization, created = update_or_create_organization(org_id)
                    if created:
                        created_count += 1
                        self.stdout.write(
                            self.style.SUCCESS(f"  Created: {organization.name}")
                        )
                    else:
                        updated_count += 1
                        self.stdout.write(f"  Updated: {organization.name}")

                    if sync_members and organization:
                        self._sync_organization_members(organization, org_id, dry_run)

                except Exception as e:
                    error_count += 1
                    self.stderr.write(
                        self.style.ERROR(f"  Failed to sync {name}: {e}")
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

    def _sync_organization_members(self, organization, org_id, dry_run):
        """Sync members for a specific organization."""
        from django.contrib.auth import get_user_model

        from django_clerk_users.client import get_clerk_client
        from django_clerk_users.organizations.models import OrganizationMember
        from django_clerk_users.utils import update_or_create_clerk_user

        User = get_user_model()
        clerk = get_clerk_client()

        try:
            response = clerk.organizations.get_membership_list(
                organization_id=org_id, limit=100
            )
            memberships = response.data if hasattr(response, "data") else response
        except Exception as e:
            self.stderr.write(
                self.style.WARNING(f"    Failed to fetch members: {e}")
            )
            return

        for membership in memberships or []:
            membership_id = getattr(membership, "id", None)
            user_data = getattr(membership, "public_user_data", None)
            user_id = getattr(user_data, "user_id", None) if user_data else None

            if not membership_id or not user_id:
                continue

            if dry_run:
                self.stdout.write(f"    Would sync member: {user_id}")
                continue

            try:
                user = User.objects.filter(clerk_id=user_id).first()
                if not user:
                    user, _ = update_or_create_clerk_user(user_id)

                OrganizationMember.objects.update_or_create(
                    clerk_membership_id=membership_id,
                    defaults={
                        "organization": organization,
                        "user": user,
                        "role": getattr(membership, "role", "member"),
                    },
                )
                self.stdout.write(f"    Synced member: {user.email}")
            except Exception as e:
                self.stderr.write(
                    self.style.WARNING(f"    Failed to sync member {user_id}: {e}")
                )
