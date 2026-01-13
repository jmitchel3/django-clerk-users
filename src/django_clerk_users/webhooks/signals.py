"""
Django signals for Clerk webhook events.

These signals allow you to hook into Clerk events without modifying
the core webhook handlers.

Example usage:

    from django.dispatch import receiver
    from django_clerk_users.webhooks.signals import clerk_user_created

    @receiver(clerk_user_created)
    def handle_new_user(sender, user, clerk_data, **kwargs):
        # Send welcome email, create related objects, etc.
        send_welcome_email(user.email)
"""

from django.dispatch import Signal

# User signals
clerk_user_created = Signal()  # Provides: user, clerk_data
clerk_user_updated = Signal()  # Provides: user, clerk_data
clerk_user_deleted = Signal()  # Provides: user, clerk_data

# Session signals
clerk_session_created = Signal()  # Provides: user, clerk_data
clerk_session_ended = Signal()  # Provides: user, clerk_data

# Organization signals (used by organizations sub-app)
clerk_organization_created = Signal()  # Provides: organization, clerk_data
clerk_organization_updated = Signal()  # Provides: organization, clerk_data
clerk_organization_deleted = Signal()  # Provides: organization, clerk_data

# Membership signals (used by organizations sub-app)
clerk_membership_created = Signal()  # Provides: membership, clerk_data
clerk_membership_updated = Signal()  # Provides: membership, clerk_data
clerk_membership_deleted = Signal()  # Provides: membership, clerk_data

# Invitation signals (used by organizations sub-app)
clerk_invitation_created = Signal()  # Provides: invitation, clerk_data
clerk_invitation_accepted = Signal()  # Provides: invitation, clerk_data
clerk_invitation_revoked = Signal()  # Provides: invitation, clerk_data
