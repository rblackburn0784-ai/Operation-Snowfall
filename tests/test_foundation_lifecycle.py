from datetime import datetime, timedelta, timezone
import pytest
from snowfall.db.store import Store, LifecycleError, RegistrationError

START = datetime(2026, 12, 20, 19, tzinfo=timezone.utc)
KEY = 'christmas-2026'

@pytest.fixture
def db(tmp_path):
    store = Store(tmp_path / 'snowfall.sqlite3')
    store.initialize()
    store.ensure_season(KEY, START)
    return store

def test_registration_exactly_seven_days_before(db):
    early = START - timedelta(days=7, microseconds=1)
    opening = START - timedelta(days=7)
    assert db.season(KEY).phase(early) == 'not_open'
    with pytest.raises(RegistrationError, match='not open'):
        db.register(KEY, 100, 'TestUser', 'Chicago', early)
    assert db.season(KEY).phase(opening) == 'registration'
    assert db.register(KEY, 100, 'TestUser', 'Chicago', opening).review_state == 'self_declared'
    assert db.season(KEY).phase(START) == 'ready'
    assert db.register(KEY, 101, 'OtherUser', 'New York', START).city == 'New York'

def test_host_start_then_exact_seven_days(db):
    season = db.season(KEY)
    with pytest.raises(LifecycleError, match='only after'):
        db.transition(KEY, 1001, 'start', START - timedelta(seconds=1), 'Opening')
    assert season.phase(START) == 'ready'
    db.transition(KEY, 1001, 'start', START, 'Host confirms opening')
    assert db.season(KEY).phase(START + timedelta(days=7, microseconds=-1)) == 'live'
    assert db.season(KEY).phase(START + timedelta(days=7)) == 'closed'
    with pytest.raises(RegistrationError, match='not open'):
        db.register(KEY, 102, 'ThirdUser', 'Detroit', START + timedelta(days=7))
    final = db.transition(KEY, 1001, 'finalize', START + timedelta(days=7), 'Game complete')
    assert final.phase(START + timedelta(days=7)) == 'finalized'
    assert db.audit_count(KEY) == 2

def test_pause_resume_freezes_time_and_extends_end(db):
    db.transition(KEY, 1001, 'start', START, 'Start')
    pause = START + timedelta(hours=20)
    db.transition(KEY, 1001, 'pause', pause, 'Hosting outage')
    assert db.season(KEY).phase(pause + timedelta(hours=72)) == 'paused'
    assert db.season(KEY).day(pause + timedelta(hours=72)) == 1
    assert db.season(KEY).projected_end(pause + timedelta(hours=2)) == START + timedelta(days=7, hours=2)
    resumed_at = pause + timedelta(hours=3, minutes=30)
    db.transition(KEY, 1001, 'resume', resumed_at, 'Outage resolved')
    restored = db.season(KEY)
    assert restored.phase(START + timedelta(days=7)) == 'live'
    assert restored.phase(START + timedelta(days=7, hours=3, minutes=30)) == 'closed'
    assert restored.paused_seconds == 3.5 * 3600
    with pytest.raises(LifecycleError):
        db.transition(KEY, 1001, 'resume', resumed_at, 'again')
    assert db.audit_count(KEY) == 3

def test_setup_immutable_once_registration_opens(db):
    now = START - timedelta(days=10)
    newer = START + timedelta(days=1)
    state = db.transition(KEY, 1001, 'setup', now, 'Schedule correction', newer)
    assert state.planned_start == newer
    assert state.registration_opens() == newer - timedelta(days=7)
    with pytest.raises(LifecycleError):
        db.transition(KEY, 1001, 'setup', newer - timedelta(days=7), 'Too late', newer + timedelta(days=2))
    assert db.audit_count(KEY) == 1

def test_persistence_and_finalization_checks(db, tmp_path):
    with pytest.raises(LifecycleError):
        db.transition(KEY, 1001, 'finalize', START, 'No early awards')
    db.transition(KEY, 1001, 'start', START, 'Starting')
    with pytest.raises(LifecycleError):
        db.transition(KEY, 1001, 'start', START + timedelta(seconds=1), 'Repeat')
    reopened = Store(db.path)
    reopened.initialize()
    assert reopened.season(KEY).phase(START + timedelta(hours=2)) == 'live'
    assert reopened.schema_version() == 3
    assert db.audit_count(KEY) == 1

def test_registration_after_pause_and_dispute_audit(db):
    db.transition(KEY, 1001, 'start', START, 'Starting')
    db.transition(KEY, 1001, 'pause', START + timedelta(days=1), 'Host outage')
    db.register(KEY, 100, 'TheDude', 'Chicago', START + timedelta(days=5))
    db.review(KEY, 1001, 100, 'flagged', 'Claim dispute', START + timedelta(days=5))
    entry = db.audit_entries(KEY)[-1]
    assert 'self_declared' in entry['before_json']
    assert 'flagged' in entry['after_json']
    assert entry['reason'] == 'Claim dispute'
    assert db.get_player(KEY, 100).review_state == 'flagged'

def test_dashboard_publish_is_idempotent(db):
    t = START - timedelta(days=1)
    db.record_published(KEY, 1001, 'dashboard', 33, 44, t)
    assert db.get_published(KEY, 'dashboard') == (33, 44)
    db.record_published(KEY, 1001, 'dashboard', 33, 55, t)
    assert db.get_published(KEY, 'dashboard') == (33, 55)
    assert db.audit_count(KEY) == 2
