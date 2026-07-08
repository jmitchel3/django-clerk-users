"""
Webhook views for Clerk events.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.http import HttpResponse, JsonResponse

from django_clerk_users.webhooks.handlers import (
    is_duplicate_webhook,
    process_webhook_event,
)
from django_clerk_users.webhooks.security import clerk_webhook_required

if TYPE_CHECKING:
    from django.http import HttpRequest

logger = logging.getLogger(__name__)


@clerk_webhook_required
def clerk_webhook_view(request: HttpRequest) -> HttpResponse:
    """
    Handle Clerk webhook events.

    This view receives webhook events from Clerk, verifies the signature,
    and processes the event.

    The @clerk_webhook_required decorator handles:
    - CSRF exemption
    - Signature verification
    - Attaching verified payload to request.clerk_webhook_data

    URL Configuration:
        Add to your urls.py:

        from django_clerk_users.webhooks import clerk_webhook_view

        urlpatterns = [
            path("webhooks/clerk/", clerk_webhook_view, name="clerk_webhook"),
        ]

    Returns:
        200 OK on success
        400 Bad Request on invalid payload
        403 Forbidden on signature verification failure
    """
    data = request.clerk_webhook_data  # type: ignore
    if not isinstance(data, dict):
        logger.warning("Webhook received invalid payload type: %s", type(data).__name__)
        return JsonResponse({"error": "Invalid payload"}, status=400)

    # Extract event metadata
    event_type = data.get("type")
    event_data = data.get("data", {})
    event_id = data.get("id", "")
    svix_id = request.headers.get("svix-id", "")

    if not event_type:
        logger.warning("Webhook received without event type")
        return JsonResponse({"error": "Missing event type"}, status=400)

    if not isinstance(event_type, str):
        logger.warning("Webhook received invalid event type: %r", event_type)
        return JsonResponse({"error": "Invalid event type"}, status=400)

    if event_data is None:
        event_data = {}
    if not isinstance(event_data, dict):
        logger.warning(
            "Webhook %s received invalid event data type: %s",
            event_type,
            type(event_data).__name__,
        )
        return JsonResponse({"error": "Invalid event data"}, status=400)

    # Check for duplicate webhook
    instance_id = _get_webhook_instance_id(event_id, svix_id)
    if instance_id:
        if is_duplicate_webhook(event_type, instance_id):
            logger.debug("Duplicate webhook ignored: %s %s", event_type, instance_id)
            return HttpResponse("OK (duplicate)", status=200)

    logger.info("Processing webhook: %s", event_type)

    # Process the event
    try:
        success = process_webhook_event(event_type, event_data)
    except Exception:
        logger.exception("Webhook processing raised unexpectedly: %s", event_type)
        success = False

    if success:
        return HttpResponse("OK", status=200)
    else:
        # Return 200 anyway to prevent Clerk from retrying
        # Log the error for monitoring
        logger.error("Webhook processing failed: %s", event_type)
        return HttpResponse("OK (processing failed)", status=200)


def _get_webhook_instance_id(event_id: Any, svix_id: Any = "") -> str:
    """Return a webhook event/message ID suitable for idempotency."""
    for instance_id in (event_id, svix_id):
        if instance_id is None:
            continue
        instance_id = str(instance_id)
        if instance_id:
            return instance_id
    return ""
