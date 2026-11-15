from datetime import datetime, timezone
import pytest
from snowfall.db.store import Store, RegistrationError, normalize_mr_username

NOW = datetime(2026, 12, 10, 12, tzinfo=timezone.utc)

@pytest.fixture
def store(tmp_path):
    db = Store(tmp_path / "registrations.sqlite3")
    db.initialize()
    return db

def test_self_declaration_and_same_user_idempotent(store):
    p = store.register("2026", 101, "TheDude", "Chicago", NOW)
    assert p.review_state == "self_declared"
    assert store.register("2026", 101, "TheDude", "Chicago", NOW) == p
    assert len(store.registrations("2026")) == 1

def test_duplicate_mr_username_case_insensitive(store):
    store.register("2026", 101, "TheDude", "Chicago", NOW)
    with pytest.raises(RegistrationError, match="already been claimed"):
        store.register("2026", 102, "theDUDE", "Detroit", NOW)

def test_disallow_unapproved_name_switch(store):
    store.register("2026", 101, "TheDude", "Chicago", NOW)
    with pytest.raises(RegistrationError, match="already registered"):
        store.register("2026", 101, "Other", "Detroit", NOW)

def test_prevent_discord_mentions_and_control_chars():
    for s in ["@everyone", "<@12345>", "A\nB", "A\x00B"]:
        with pytest.raises(RegistrationError):
            normalize_mr_username(s)

def test_review_is_audited(store):
    store.register("2026", 101, "TheDude", "Chicago", NOW)
    store.review("2026", 999, 101, "flagged", "Disputed MR name", NOW)
    assert store.get_player("2026", 101).review_state == "flagged"
    assert store.audit_count("2026") == 1
    with pytest.raises(ValueError):
        store.review("2026", 999, 101, "cleared", "", NOW)
