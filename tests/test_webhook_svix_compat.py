"""
verify_clerk_webhook must return the payload on svix 1.x and 2.x.

svix 1.x ``Webhook.verify`` returns the parsed JSON; svix 2.x returns None.
"""

import base64
import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from django.test import RequestFactory
from svix.webhooks import Webhook

from django_clerk_users.exceptions import ClerkWebhookError
from django_clerk_users.webhooks.security import verify_clerk_webhook

SECRET = "whsec_" + base64.b64encode(b"svix-compat-test-secret-32bytes!").decode()


def signed_request(body: str, secret: str = SECRET):
    now = datetime.now(timezone.utc)
    signature = Webhook(secret).sign("msg_compat", now, body)
    return RequestFactory().post(
        "/webhooks/clerk/",
        data=body,
        content_type="application/json",
        HTTP_SVIX_ID="msg_compat",
        HTTP_SVIX_TIMESTAMP=str(int(now.timestamp())),
        HTTP_SVIX_SIGNATURE=signature,
    )


PAYLOAD = {"type": "user.updated", "data": {"id": "user_compat"}}
BODY = json.dumps(PAYLOAD)


def test_installed_svix_returns_payload():
    assert verify_clerk_webhook(signed_request(BODY), signing_key=SECRET) == PAYLOAD


@pytest.mark.parametrize(
    "verify_result",
    [None, PAYLOAD],
    ids=["svix-2-returns-none", "svix-1-returns-payload"],
)
def test_both_svix_return_contracts(verify_result):
    with patch.object(Webhook, "verify", return_value=verify_result) as verify:
        payload = verify_clerk_webhook(signed_request(BODY), signing_key=SECRET)
    verify.assert_called_once()
    assert payload == PAYLOAD


def test_bad_signature_still_rejected():
    request = signed_request(BODY)
    request.META["HTTP_SVIX_SIGNATURE"] = "v1,bm90LWEtcmVhbC1zaWduYXR1cmU="
    with pytest.raises(ClerkWebhookError, match="verification failed"):
        verify_clerk_webhook(request, signing_key=SECRET)


@pytest.mark.parametrize("body", ["[1, 2]", '"text"', "null"])
def test_non_object_payload_rejected(body):
    with pytest.raises(ClerkWebhookError, match="JSON object"):
        verify_clerk_webhook(signed_request(body), signing_key=SECRET)


def test_invalid_json_after_valid_signature_rejected():
    with pytest.raises(ClerkWebhookError, match="verification error"):
        verify_clerk_webhook(signed_request("{not json"), signing_key=SECRET)
