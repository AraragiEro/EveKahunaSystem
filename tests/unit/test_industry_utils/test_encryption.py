# -*- coding: utf-8 -*-
"""Unit tests for encode_share_code and decode_share_code in config_utils.

Tests round-trip encryption/decryption and error cases without
depending on config.toml or any database modules.
"""

import importlib
import pytest
from cryptography.fernet import Fernet
from unittest.mock import patch

from src_v2.core.utils import KahunaException


# ---------------------------------------------------------------------------
# Use importlib to defer module loading, avoiding config-module side effects
# at import time.  The module is loaded once per test session via fixture.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def config_utils_mod():
    """Import config_utils lazily via importlib."""
    return importlib.import_module(
        "src_v2.model.EVE.industry.industry_utils.config_utils"
    )


@pytest.fixture
def fernet_key():
    """Generate a real, deterministic Fernet key for testing."""
    return Fernet.generate_key()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestShareCodeEncryption:
    """Tests for encode_share_code / decode_share_code round-trip."""

    def test_round_trip_integers(self, config_utils_mod, fernet_key):
        """encode([1,2,3]) → decode → [1,2,3]"""
        with patch.object(
            config_utils_mod, "_get_encryption_key", return_value=fernet_key
        ):
            encoded = config_utils_mod.encode_share_code([1, 2, 3])
            decoded = config_utils_mod.decode_share_code(encoded)
            assert decoded == [1, 2, 3]

    def test_round_trip_empty_list(self, config_utils_mod, fernet_key):
        """encode([]) → decode → []"""
        with patch.object(
            config_utils_mod, "_get_encryption_key", return_value=fernet_key
        ):
            encoded = config_utils_mod.encode_share_code([])
            decoded = config_utils_mod.decode_share_code(encoded)
            assert decoded == []

    def test_round_trip_mixed_types(self, config_utils_mod, fernet_key):
        """encode(["a", 123, "b"]) → decode → ["a", 123, "b"]"""
        with patch.object(
            config_utils_mod, "_get_encryption_key", return_value=fernet_key
        ):
            encoded = config_utils_mod.encode_share_code(["a", 123, "b"])
            decoded = config_utils_mod.decode_share_code(encoded)
            assert decoded == ["a", 123, "b"]

    def test_decode_invalid_share_code_raises(self, config_utils_mod, fernet_key):
        """decode with a garbage (non-Fernet) string raises KahunaException."""
        with patch.object(
            config_utils_mod, "_get_encryption_key", return_value=fernet_key
        ):
            with pytest.raises(KahunaException):
                config_utils_mod.decode_share_code(
                    "this-is-garbage-not-a-valid-fernet-token"
                )

    def test_decode_empty_string_raises(self, config_utils_mod, fernet_key):
        """decode with an empty string raises KahunaException."""
        with patch.object(
            config_utils_mod, "_get_encryption_key", return_value=fernet_key
        ):
            with pytest.raises(KahunaException):
                config_utils_mod.decode_share_code("")

    def test_different_ciphertexts_same_plaintext(
        self, config_utils_mod, fernet_key
    ):
        """encode produces different ciphertext each time (random IV),
        but all ciphertexts decode to the same original value."""
        original = [1, 2, 3]
        with patch.object(
            config_utils_mod, "_get_encryption_key", return_value=fernet_key
        ):
            encoded1 = config_utils_mod.encode_share_code(original)
            encoded2 = config_utils_mod.encode_share_code(original)

            assert (
                encoded1 != encoded2
            ), "ciphertexts should differ due to random IV"
            assert config_utils_mod.decode_share_code(encoded1) == original
            assert config_utils_mod.decode_share_code(encoded2) == original
