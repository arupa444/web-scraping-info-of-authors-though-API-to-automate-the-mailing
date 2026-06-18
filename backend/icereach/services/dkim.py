"""DKIM key generation and message signing (spec §8.2).

On sending-domain setup the platform generates a DKIM selector + RSA-2048
keypair. The public key is rendered as a DNS ``TXT`` record for the operator
to publish; the private key is stored encrypted on ``SendingDomain`` and used
by the worker to DKIM-sign every outbound message before handing it to the
SMTP adapter.

This module owns the cryptographic primitives only:

* :func:`generate_keypair` — make a fresh RSA-2048 keypair and the matching
  ``v=DKIM1`` DNS TXT value.
* :func:`sign_message` — produce a ``DKIM-Signature`` header for a raw
  RFC 822 message using ``dkimpy``.
"""

from __future__ import annotations

import base64

import dkim as dkimpy
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# RSA-2048 is the spec-mandated key size (§8.2); also the floor most mailbox
# providers accept for DKIM today.
_RSA_KEY_BITS = 2048
_RSA_PUBLIC_EXPONENT = 65537

# Standard header set signed for outbound mail. Order matters for the DKIM
# ``h=`` tag; these are the headers a typical message always carries.
_SIGNED_HEADERS = [
    b"From",
    b"To",
    b"Subject",
    b"Date",
    b"MIME-Version",
    b"Content-Type",
]


def generate_keypair() -> tuple[str, str]:
    """Generate an RSA-2048 DKIM keypair.

    Returns:
        A ``(pem_private_key, dns_txt_value)`` tuple where:

        * ``pem_private_key`` is the PKCS#8 PEM-encoded private key
          (``-----BEGIN PRIVATE KEY-----`` ...), suitable for storing as an
          encrypted string on ``SendingDomain`` and feeding to
          :func:`sign_message`.
        * ``dns_txt_value`` is the DKIM DNS TXT record value of the form
          ``v=DKIM1; k=rsa; p=<base64 DER SubjectPublicKeyInfo>`` to publish
          at ``<selector>._domainkey.<domain>``.
    """
    private_key = rsa.generate_private_key(
        public_exponent=_RSA_PUBLIC_EXPONENT,
        key_size=_RSA_KEY_BITS,
    )

    pem_private_key = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")

    # DKIM publishes the public key as base64 of the DER SubjectPublicKeyInfo.
    public_der = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_b64 = base64.b64encode(public_der).decode("ascii")
    dns_txt_value = f"v=DKIM1; k=rsa; p={public_b64}"

    return pem_private_key, dns_txt_value


def sign_message(
    message_bytes: bytes,
    domain: str,
    selector: str,
    private_key_pem: str,
) -> bytes:
    """DKIM-sign a raw RFC 822 message.

    Args:
        message_bytes: The full raw message (headers + CRLF separator + body).
        domain: The signing domain placed in the DKIM ``d=`` tag; for DMARC
            alignment this is the verified ``SendingDomain`` (§8.4).
        selector: The DKIM selector placed in the ``s=`` tag; the public key
            lives at ``<selector>._domainkey.<domain>``.
        private_key_pem: PEM-encoded RSA private key, as returned by
            :func:`generate_keypair`.

    Returns:
        The ``DKIM-Signature: ...\\r\\n`` header as bytes, ready to prepend to
        the outbound message.
    """
    # ``dkimpy`` signs over whichever of ``include_headers`` are present in the
    # message, so passing a superset is safe for minimal test messages.
    signature = dkimpy.sign(
        message=message_bytes,
        selector=selector.encode("ascii"),
        domain=domain.encode("ascii"),
        privkey=private_key_pem.encode("ascii"),
        include_headers=_SIGNED_HEADERS,
        canonicalize=(b"relaxed", b"simple"),
        signature_algorithm=b"rsa-sha256",
    )
    return signature
