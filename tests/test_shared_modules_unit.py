"""Direct unit tests for shared nexus_common modules.

Tests:
  IdempotencyStore — state machine (new key, duplicate, expired, mismatch,
                     capacity eviction, save_response, compaction)
  triage_rules     — evaluate_triage boundary suite (keyword + vital thresholds)
  auth             — mint_jwt / verify_jwt roundtrip, expiry, scope, bad secret
"""

from __future__ import annotations

import pathlib
import sys
import time

import pytest

# ── Project root on sys.path ──────────────────────────────────────────────────
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from shared.nexus_common.auth import AuthError, mint_jwt, verify_jwt  # noqa: E402
from shared.nexus_common.idempotency import IdempotencyStore  # noqa: E402
from shared.nexus_common.triage_rules import evaluate_triage  # noqa: E402

_SECRET = "dev-secret-change-me"


# ═══════════════════════════════════════════════════════════════════════════════
# IdempotencyStore — state machine tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestIdempotencyStoreNewKey:
    def test_new_key_is_not_duplicate(self):
        store = IdempotencyStore()
        result = store.check_or_register("key-001", dedup_window_ms=60_000)
        assert result.is_duplicate is False

    def test_new_key_first_seen_at_is_close_to_now(self):
        store = IdempotencyStore()
        before = time.time()
        result = store.check_or_register("key-002", dedup_window_ms=60_000)
        after = time.time()
        assert before <= result.first_seen_at <= after

    def test_new_key_stores_scope(self):
        store = IdempotencyStore()
        result = store.check_or_register("key-003", dedup_window_ms=60_000, scope="triage")
        assert result.scope == "triage"

    def test_new_key_stores_payload_hash(self):
        store = IdempotencyStore()
        result = store.check_or_register("key-004", dedup_window_ms=60_000, payload_hash="abc123")
        assert result.payload_hash == "abc123"


class TestIdempotencyStoreDuplicate:
    def test_second_call_is_duplicate(self):
        store = IdempotencyStore()
        store.check_or_register("dup-001", dedup_window_ms=60_000)
        result = store.check_or_register("dup-001", dedup_window_ms=60_000)
        assert result.is_duplicate is True

    def test_duplicate_returns_same_first_seen_at(self):
        store = IdempotencyStore()
        first = store.check_or_register("dup-002", dedup_window_ms=60_000)
        second = store.check_or_register("dup-002", dedup_window_ms=60_000)
        assert second.first_seen_at == first.first_seen_at

    def test_duplicate_with_same_hash_no_mismatch(self):
        store = IdempotencyStore()
        store.check_or_register("dup-003", dedup_window_ms=60_000, payload_hash="hash-a")
        result = store.check_or_register("dup-003", dedup_window_ms=60_000, payload_hash="hash-a")
        assert result.payload_mismatch is False

    def test_duplicate_with_different_hash_mismatch(self):
        store = IdempotencyStore()
        store.check_or_register("dup-004", dedup_window_ms=60_000, payload_hash="hash-a")
        result = store.check_or_register("dup-004", dedup_window_ms=60_000, payload_hash="hash-b")
        assert result.payload_mismatch is True

    def test_scope_isolates_keys(self):
        store = IdempotencyStore()
        store.check_or_register("shared-key", dedup_window_ms=60_000, scope="scope-a")
        result = store.check_or_register("shared-key", dedup_window_ms=60_000, scope="scope-b")
        # Different scope → different full_key → not a duplicate
        assert result.is_duplicate is False

    def test_same_key_same_scope_is_duplicate(self):
        store = IdempotencyStore()
        store.check_or_register("k", dedup_window_ms=60_000, scope="s1")
        result = store.check_or_register("k", dedup_window_ms=60_000, scope="s1")
        assert result.is_duplicate is True


class TestIdempotencyStoreExpiry:
    def test_expired_key_is_not_duplicate(self):
        clock = [0.0]

        def _clock():
            return clock[0]

        store = IdempotencyStore(clock=_clock)
        store.check_or_register("exp-001", dedup_window_ms=1_000)  # 1 s TTL

        # Advance clock past TTL
        clock[0] = 2.0
        result = store.check_or_register("exp-001", dedup_window_ms=1_000)
        assert result.is_duplicate is False

    def test_key_within_window_is_still_duplicate(self):
        clock = [0.0]

        def _clock():
            return clock[0]

        store = IdempotencyStore(clock=_clock)
        store.check_or_register("exp-002", dedup_window_ms=5_000)  # 5 s TTL

        clock[0] = 4.9
        result = store.check_or_register("exp-002", dedup_window_ms=5_000)
        assert result.is_duplicate is True


class TestIdempotencyStoreCapacityEviction:
    def test_over_capacity_evicts_oldest(self):
        store = IdempotencyStore(max_entries=3)
        for i in range(3):
            store.check_or_register(f"cap-{i}", dedup_window_ms=60_000)

        # Adding a 4th entry must evict the oldest (cap-0)
        store.check_or_register("cap-3", dedup_window_ms=60_000)

        # cap-0 was evicted — checking again is NOT a duplicate
        result = store.check_or_register("cap-0", dedup_window_ms=60_000)
        assert result.is_duplicate is False

    def test_capacity_one_always_has_latest(self):
        store = IdempotencyStore(max_entries=1)
        store.check_or_register("only-a", dedup_window_ms=60_000)  # [only-a]
        store.check_or_register("only-b", dedup_window_ms=60_000)  # evicts only-a → [only-b]
        # only-b is the most-recently registered entry — must still be a duplicate
        result_b = store.check_or_register("only-b", dedup_window_ms=60_000)
        assert result_b.is_duplicate is True


class TestIdempotencyStoreSaveResponse:
    def test_save_response_is_returned_on_duplicate(self):
        store = IdempotencyStore()
        store.check_or_register("save-001", dedup_window_ms=60_000)
        store.save_response("save-001", {"task_id": "t-001", "status": "ok"})

        result = store.check_or_register("save-001", dedup_window_ms=60_000)
        assert result.is_duplicate is True
        assert result.cached_response is not None
        assert result.cached_response.get("task_id") == "t-001"

    def test_save_response_noop_for_unknown_key(self):
        store = IdempotencyStore()
        # Should not raise
        store.save_response("nonexistent", {"task_id": "x"})

    def test_save_response_with_scope(self):
        store = IdempotencyStore()
        store.check_or_register("save-s", dedup_window_ms=60_000, scope="scoped")
        store.save_response("save-s", {"task_id": "t-scoped"}, scope="scoped")
        result = store.check_or_register("save-s", dedup_window_ms=60_000, scope="scoped")
        assert result.cached_response is not None
        assert result.cached_response.get("task_id") == "t-scoped"


class TestIdempotencyStoreResponseCompaction:
    def test_large_response_is_compacted_to_priority_keys(self):
        # Use a very small max_cached_response_bytes to force compaction
        store = IdempotencyStore(max_cached_response_bytes=300)
        store.check_or_register("compact-001", dedup_window_ms=60_000)
        big_response = {
            "task_id": "t-compact",
            "trace_id": "tr-001",
            "status": "ok",
            "huge_field": "x" * 10_000,
        }
        store.save_response("compact-001", big_response)
        result = store.check_or_register("compact-001", dedup_window_ms=60_000)
        assert result.cached_response is not None
        # task_id and status are priority keys and must survive compaction
        assert result.cached_response.get("task_id") == "t-compact"
        assert result.cached_response.get("_idempotency_truncated") is True

    def test_small_response_not_truncated(self):
        store = IdempotencyStore()
        store.check_or_register("compact-002", dedup_window_ms=60_000)
        small_response = {"task_id": "t-small", "status": "ok"}
        store.save_response("compact-002", small_response)
        result = store.check_or_register("compact-002", dedup_window_ms=60_000)
        assert result.cached_response is not None
        assert result.cached_response.get("_idempotency_truncated") is None


class TestIdempotencyStoreValidation:
    def test_zero_dedup_window_raises(self):
        store = IdempotencyStore()
        with pytest.raises(ValueError, match="dedup_window_ms must be > 0"):
            store.check_or_register("bad", dedup_window_ms=0)

    def test_negative_dedup_window_raises(self):
        store = IdempotencyStore()
        with pytest.raises(ValueError, match="dedup_window_ms must be > 0"):
            store.check_or_register("bad", dedup_window_ms=-100)

    def test_close_clears_store(self):
        store = IdempotencyStore()
        store.check_or_register("close-001", dedup_window_ms=60_000)
        store.close()
        # After close, entry is gone
        result = store.check_or_register("close-001", dedup_window_ms=60_000)
        assert result.is_duplicate is False


# ═══════════════════════════════════════════════════════════════════════════════
# triage_rules — evaluate_triage boundary suite
# ═══════════════════════════════════════════════════════════════════════════════

class TestTriageRulesKeywords:
    @pytest.mark.parametrize("complaint,expected", [
        ("chest pain radiating to jaw", "ESI-2"),
        ("CHEST tightness and sweating", "ESI-2"),   # case-insensitive
        ("shortness of breath at rest", "ESI-2"),
        ("confusion and altered GCS", "ESI-2"),
        ("laceration to forearm", "ESI-4"),
        ("general malaise", "ESI-3"),                # default
        ("headache mild", "ESI-3"),
        ("", "ESI-3"),                               # empty complaint → default
    ])
    def test_keyword_rules(self, complaint, expected):
        result = evaluate_triage(complaint, vitals={})
        assert result == expected, (
            f"complaint={complaint!r}: expected {expected}, got {result}"
        )

    def test_chest_keyword_wins_over_default(self):
        assert evaluate_triage("chest discomfort") == "ESI-2"

    def test_laceration_only_esi4_not_esi2(self):
        # laceration matches ESI-4 rule but NOT ESI-2 (no chest/dyspnea/confusion keyword)
        assert evaluate_triage("laceration on hand") == "ESI-4"

    def test_multiple_keywords_first_match_wins(self):
        # "chest" rule comes before "laceration" rule in fallback order → ESI-2
        result = evaluate_triage("chest laceration")
        assert result == "ESI-2"


class TestTriageRulesVitalThresholds:
    @pytest.mark.parametrize("spo2,expected", [
        (89.9, "ESI-2"),    # strictly < 90
        (89,   "ESI-2"),
        (90,   "ESI-3"),    # NOT < 90 → does not trigger ESI-2
        (95,   "ESI-3"),
        (100,  "ESI-3"),
    ])
    def test_spo2_boundary(self, spo2, expected):
        result = evaluate_triage("general malaise", vitals={"spo2": spo2})
        assert result == expected, (
            f"spo2={spo2}: expected {expected}, got {result}"
        )

    @pytest.mark.parametrize("temp_c,expected", [
        (39.0, "ESI-2"),    # >= 39.0 → ESI-2
        (39.1, "ESI-2"),
        (40.5, "ESI-2"),
        (38.9, "ESI-3"),    # < 39.0 → default
        (37.0, "ESI-3"),
        (36.5, "ESI-3"),
    ])
    def test_temp_boundary(self, temp_c, expected):
        result = evaluate_triage("general malaise", vitals={"temp_c": temp_c})
        assert result == expected, (
            f"temp_c={temp_c}: expected {expected}, got {result}"
        )

    def test_low_spo2_overrides_laceration_keyword(self):
        # spo2 < 90 rule (ESI-2) comes before laceration rule (ESI-4)
        result = evaluate_triage("laceration", vitals={"spo2": 85})
        assert result == "ESI-2"

    def test_missing_vital_does_not_crash(self):
        # No vitals provided → falls back to keyword/default rules
        result = evaluate_triage("headache", vitals={})
        assert result in ("ESI-2", "ESI-3", "ESI-4")

    def test_non_numeric_vital_is_skipped(self):
        # Non-numeric vital must not crash; should fall to next rule
        result = evaluate_triage("general malaise", vitals={"spo2": "unavailable"})
        assert result in ("ESI-2", "ESI-3", "ESI-4")

    def test_none_vitals_treated_as_empty(self):
        result = evaluate_triage("general malaise", vitals=None)
        assert result == "ESI-3"


class TestTriageRulesCombinations:
    def test_chest_plus_low_spo2_esi2(self):
        # Both chest keyword and low SpO2 → ESI-2 (keyword first, same result)
        result = evaluate_triage("chest pain", vitals={"spo2": 88})
        assert result == "ESI-2"

    def test_high_temp_plus_laceration_temp_wins(self):
        # temp_c >= 39.0 is checked before laceration keyword
        result = evaluate_triage("laceration", vitals={"temp_c": 39.5})
        assert result == "ESI-2"


# ═══════════════════════════════════════════════════════════════════════════════
# auth — mint_jwt / verify_jwt roundtrip
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuthJwtRoundtrip:
    def test_mint_and_verify_success(self):
        token = mint_jwt("test-sub", _SECRET, scope="nexus:invoke")
        payload = verify_jwt(token, _SECRET)
        assert payload["sub"] == "test-sub"
        assert "nexus:invoke" in payload["scope"].split()

    def test_payload_contains_exp_and_iat(self):
        before = int(time.time())
        token = mint_jwt("test-sub", _SECRET, ttl_seconds=3600)
        payload = verify_jwt(token, _SECRET)
        after = int(time.time())
        assert before <= payload["iat"] <= after
        assert payload["exp"] >= before + 3590  # allow 10 s tolerance

    def test_wrong_secret_raises_auth_error(self):
        token = mint_jwt("test-sub", _SECRET)
        with pytest.raises(AuthError):
            verify_jwt(token, "wrong-secret")

    def test_expired_token_raises_auth_error(self):
        token = mint_jwt("test-sub", _SECRET, ttl_seconds=-1)
        with pytest.raises(AuthError, match="[Ee]xpired"):
            verify_jwt(token, _SECRET)

    def test_malformed_token_raises_auth_error(self):
        with pytest.raises(AuthError):
            verify_jwt("not.a.valid.jwt.string", _SECRET)

    def test_required_scope_passes(self):
        token = mint_jwt("test-sub", _SECRET, scope="nexus:invoke read:data")
        payload = verify_jwt(token, _SECRET, required_scope="nexus:invoke")
        assert payload["sub"] == "test-sub"

    def test_required_scope_missing_raises_auth_error(self):
        token = mint_jwt("test-sub", _SECRET, scope="read:only")
        with pytest.raises(AuthError, match="[Ss]cope"):
            verify_jwt(token, _SECRET, required_scope="nexus:invoke")

    def test_multiple_scopes_in_token(self):
        scope = "nexus:invoke encounter.read patient.read"
        token = mint_jwt("test-sub", _SECRET, scope=scope)
        payload = verify_jwt(token, _SECRET, required_scope="encounter.read")
        assert "encounter.read" in payload["scope"].split()

    def test_custom_ttl(self):
        token = mint_jwt("test-sub", _SECRET, ttl_seconds=7200)
        payload = verify_jwt(token, _SECRET)
        assert payload["exp"] - payload["iat"] >= 7190  # allow 10 s skew

    def test_subject_preserved(self):
        subjects = ["agent-001", "test-harness", "insurer-agent", "triage-nurse"]
        for sub in subjects:
            token = mint_jwt(sub, _SECRET)
            payload = verify_jwt(token, _SECRET)
            assert payload["sub"] == sub

    def test_default_scope_is_nexus_invoke(self):
        token = mint_jwt("test-sub", _SECRET)
        payload = verify_jwt(token, _SECRET)
        assert "nexus:invoke" in payload["scope"].split()
