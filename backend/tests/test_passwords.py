"""Tests for Argon2id password hashing helpers."""

from icereach.security.passwords import hash_password, verify_password


def test_verify_accepts_correct_password():
    pw = "correct horse battery staple"
    assert verify_password(hash_password(pw), pw) is True


def test_verify_rejects_wrong_password():
    h = hash_password("correct horse battery staple")
    assert verify_password(h, "Tr0ubador&3") is False


def test_two_hashes_of_same_password_differ():
    pw = "same-password"
    assert hash_password(pw) != hash_password(pw)


def test_verify_returns_false_on_malformed_hash():
    assert verify_password("not-a-real-hash", "anything") is False
