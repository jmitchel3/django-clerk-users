"""
Webhook security utilities for Clerk.

Uses Svix for webhook signature verification.
"""

from __future__ import annotations

import functools
import logging
from typing import TYPE_CHECKING, Any, Callable

from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from svix.webhooks import Webhook, WebhookVerificationError

from django_clerk_users.exceptions import ClerkWebhookError
from django_clerk_users.settings import CLERK_WEBHOOK_SIGNING_KEY

if TYPE_CHECKING:
    from django.http import HttpRequest

logger = logging.getLogger(__name__)


def verify_clerk_webhook(request: "HttpRequest") -> dict[str, Any]:
    """
    Verify a Clerk webhook signature using Svix.

    Args:
        request: The Django HTTP request containing the webhook payload.

    Returns:
        The verified webhook payload as a dictionary.

    Raises:
        ClerkWebhookError: If verification fails or signing key is not configured.
    """
    if not CLERK_WEBHOOK_SIGNING_KEY:
        raise ClerkWebhookError(
            "CLERK_WEBHOOK_SIGNING_KEY is not configured. "
            "Set it in your Django settings to enable webhook verification."
        )

    try:
        wh = Webhook(CLERK_WEBHOOK_SIGNING_KEY)

        # Svix expects specific headers
        headers = {
            "svix-id": request.headers.get("svix-id", ""),
            "svix-timestamp": request.headers.get("svix-timestamp", ""),
            "svix-signature": request.headers.get("svix-signature", ""),
        }

        # Verify and parse the payload
        payload = wh.verify(request.body, headers)
        return payload

    except WebhookVerificationError as e:
        logger.warning(f"Webhook verification failed: {e}")
        raise ClerkWebhookError(f"Webhook verification failed: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error during webhook verification: {e}")
        raise ClerkWebhookError(f"Webhook verification error: {e}") from e


def clerk_webhook_required(view_func: Callable) -> Callable:
    """
    Decorator that verifies Clerk webhook signatures.

    Use this decorator on webhook view functions to automatically
    verify the webhook signature and attach the verified payload
    to the request.

    Example:
        from django_clerk_users.webhooks import clerk_webhook_required

        @clerk_webhook_required
        def my_webhook_view(request):
            data = request.clerk_webhook_data
            # Process the webhook...
            return HttpResponse("OK")

    The decorator:
    1. Exempts the view from CSRF protection (webhooks can't have CSRF tokens)
    2. Verifies the Svix signature
    3. Attaches the verified payload to request.clerk_webhook_data
    4. Returns 400/403 responses on verification failure
    """

    @csrf_exempt
    @functools.wraps(view_func)
    def wrapper(request: "HttpRequest", *args, **kwargs):
        if request.method != "POST":
            return HttpResponseBadRequest("Only POST requests are allowed")

        try:
            payload = verify_clerk_webhook(request)
        except ClerkWebhookError as e:
            logger.warning(f"Webhook verification failed: {e}")
            return HttpResponseForbidden(str(e))

        # Attach verified payload to request
        request.clerk_webhook_data = payload  # type: ignore

        return view_func(request, *args, **kwargs)

    return wrapper
