"""Tests for CryptoService password hashing."""
import pytest
from api.services.crypto_service import CryptoService


def test_hash_is_not_plaintext():
    h = CryptoService.get_password_hash("secret")
    assert h != "secret"


def test_verify_correct_password():
    h = CryptoService.get_password_hash("mypassword")
    assert CryptoService.verify_password("mypassword", h) is True


def test_verify_wrong_password():
    h = CryptoService.get_password_hash("correct")
    assert CryptoService.verify_password("wrong", h) is False


def test_different_salts_for_same_password():
    h1 = CryptoService.get_password_hash("same")
    h2 = CryptoService.get_password_hash("same")
    assert h1 != h2


def test_each_hash_verifies_independently():
    h1 = CryptoService.get_password_hash("same")
    h2 = CryptoService.get_password_hash("same")
    assert CryptoService.verify_password("same", h1) is True
    assert CryptoService.verify_password("same", h2) is True


def test_hash_is_bcrypt_format():
    h = CryptoService.get_password_hash("test")
    assert h.startswith("$2b$")


def test_empty_password_hashes():
    h = CryptoService.get_password_hash("")
    assert CryptoService.verify_password("", h) is True


def test_unicode_password():
    password = "pässwörд"
    h = CryptoService.get_password_hash(password)
    assert CryptoService.verify_password(password, h) is True


def test_long_password():
    password = "a" * 72
    h = CryptoService.get_password_hash(password)
    assert CryptoService.verify_password(password, h) is True
