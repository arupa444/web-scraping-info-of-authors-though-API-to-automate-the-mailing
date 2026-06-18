"""Tests for the DKIM keygen + signing service (icereach.services.dkim)."""

from cryptography.hazmat.primitives import serialization

from icereach.services.dkim import generate_keypair, sign_message

# A tiny, well-formed RFC 822 message (CRLF line endings, blank-line body sep).
_SAMPLE_MESSAGE = (
    b"From: Sender <sender@example.com>\r\n"
    b"To: Recipient <rcpt@example.org>\r\n"
    b"Subject: Hello\r\n"
    b"Date: Thu, 19 Jun 2026 00:00:00 +0000\r\n"
    b"MIME-Version: 1.0\r\n"
    b"Content-Type: text/plain; charset=utf-8\r\n"
    b"\r\n"
    b"This is a test body.\r\n"
)


def test_generate_keypair_returns_pem_private_and_dkim_txt():
    """generate_keypair yields a usable PEM private key and a v=DKIM1 TXT."""
    private_pem, dns_txt = generate_keypair()

    # Private key is PEM and actually parses as a private key.
    assert isinstance(private_pem, str)
    assert "-----BEGIN PRIVATE KEY-----" in private_pem
    assert "-----END PRIVATE KEY-----" in private_pem
    serialization.load_pem_private_key(private_pem.encode("ascii"), password=None)

    # DNS TXT value is a proper DKIM record with a base64 public key.
    assert isinstance(dns_txt, str)
    assert dns_txt.startswith("v=DKIM1; k=rsa; p=")
    public_b64 = dns_txt.split("p=", 1)[1]
    assert public_b64  # non-empty key material


def test_generate_keypair_returns_distinct_keys():
    """Each call produces a fresh keypair."""
    pem_a, txt_a = generate_keypair()
    pem_b, txt_b = generate_keypair()
    assert pem_a != pem_b
    assert txt_a != txt_b


def test_sign_message_returns_dkim_signature_header():
    """sign_message produces a DKIM-Signature header for a tiny message."""
    private_pem, _ = generate_keypair()

    signature = sign_message(
        message_bytes=_SAMPLE_MESSAGE,
        domain="example.com",
        selector="ir1",
        private_key_pem=private_pem,
    )

    assert isinstance(signature, bytes)
    assert signature.startswith(b"DKIM-Signature:")
    assert signature.endswith(b"\r\n")
    # The signing domain and selector are reflected in the header tags.
    assert b"d=example.com" in signature
    assert b"s=ir1" in signature
