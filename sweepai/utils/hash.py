import hashlib
import hmac

from sweepai.config.server import WEBHOOK_SECRET


def hash_sha256(text: str):
    return hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()

def verify_signature(
    payload_body: bytes,
    signature_header: str | None
):
    """Verify that the payload was sent from GitHub by validating SHA256.

    Raise and return 403 if not authorized.

    Args:
        payload_body: original request body to verify (request.body())
        signature_header: header received from GitHub (x-hub-signature-256)
    """
    if not WEBHOOK_SECRET:
        # If the secret is not set, we can't verify the signature
        return True
    if not signature_header:
        return False
    hash_object = hmac.new(
        WEBHOOK_SECRET.encode('utf-8'),
        msg=payload_body,
        digestmod=hashlib.sha256
    )
    expected_signature = "sha256=" + hash_object.hexdigest()
    if not hmac.compare_digest(expected_signature, signature_header):
        return False
    return True