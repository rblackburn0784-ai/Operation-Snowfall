"""Single-application, channel-scoped disposable event-day rehearsals.

All live commands continue to use the live settings/store outside the selected
practice channel. The real scheduler and broadcast publisher ALWAYS retain the
live settings/store; a practice session never writes to production.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import threading
from uuid import uuid4

from snowfall.db.store import Store, Player
from snowfall.services.world import WorldEngine, THEMES
from snowfall.services.broadcast import DAY_DETAILS

_ROUTE = ContextVar("snowfall_interaction_route", default="live")


class PracticeError(ValueError):
    """A rehearsal is not permitted or the selected test has expired."""


class PracticeStore(Store):
    """Revocable practice store. Stale buttons cannot recreate a deleted DB."""

    def __init__(self, path: Path):
        super().__init__(path)
        self._lock = threading.RLock()
        self.active = True

    @contextmanager
    def connect(self):
        with self._lock:
            if not self.active:
                raise PracticeError("This test day has ended. Open a fresh test menu.")
            with super().connect() as connection:
                yield connection

    def retire(self) -> None:
        # Wait for any currently open database transaction before revoking.
        with self._lock:
            self.active = False


@dataclass(frozen=True)
class PracticeSession:
    id: str
    day: int
    channel_id: int
    settings: object
    store: PracticeStore
    started_at_utc: datetime


class PracticeManager:
    """One active practice day within the same Discord app and guild."""

    def __init__(self, live_settings, live_store):
        self.live_settings = live_settings
        self.live_store = live_store
        self._lock = threading.RLock()
        self._session: PracticeSession | None = None
        # Always separate from the real DB and kept beneath an ignored data/ path.
        self.practice_dir = live_store.path.parent / "practice"
        self.archive_dir = live_store.path.parent / "practice_archives"

    @property
    def session(self) -> PracticeSession | None:
        with self._lock:
            return self._session

    def for_interaction(self, channel_id: int | None) -> bool:
        """Called by slash group checks in each Discord interaction task."""
        with self._lock:
            active = bool(self._session and self._session.channel_id == channel_id)
        _ROUTE.set("practice" if active else "live")
        return active

    def selected(self):
        if _ROUTE.get() == "practice":
            current = self.session
            if current and current.store.active:
                return current.settings, current.store
            # Fail closed; never silently fall through to production.
            raise PracticeError("That test day has ended; run the command again.")
        return self.live_settings, self.live_store

    def _check_live(self, now: datetime) -> None:
        # No switching the bot into a test session while official scoring runs.
        phase = self.live_store.season(self.live_settings.season_key).phase(now)
        if phase in ("live", "paused", "closed", "finalized"):
            raise PracticeError("Test sessions are blocked after live kickoff. "
                                "Finish testing before the real event begins.")

    def _new(self, day: int, channel_id: int, host_id: int, now: datetime,
             players: list[Player] = ()) -> PracticeSession:
        if not 1 <= day <= 7:
            raise PracticeError("Select a day from 1 to 7")
        if channel_id in (self.live_settings.announcement_channel_id,
                          self.live_settings.leaderboard_channel_id):
            raise PracticeError("Choose a separate test channel, not #leaderboard or #Announcements")
        if not channel_id or channel_id <= 0:
            raise PracticeError("Choose an actual text channel for the test")
        self.practice_dir.mkdir(parents=True, exist_ok=True)
        session_id = uuid4().hex
        path = self.practice_dir / f"day-{day}-{session_id}.sqlite3"
        if path.resolve() == self.live_store.path.resolve():
            raise PracticeError("Practice storage must never match the live database")
        day_start = now - timedelta(days=day - 1, seconds=3)
        # Every day lasts 24 effective hours, but a host may end it at any time.
        test_settings = replace(self.live_settings,
                                season_key=f"rehearsal-{session_id}",
                                event_name=f"Operation Snowfall — TEST DAY {day}",
                                starts_at_utc=day_start,
                                database_path=path,
                                leaderboard_channel_id=0,
                                announcement_channel_id=0,
                                backup_dir=self.archive_dir,
                                mode="practice",
                                session_id=session_id)
        store = PracticeStore(path)
        try:
            store.initialize()
            store.ensure_season(test_settings.season_key, day_start)
            for p in players:
                # Mirror identities only *within practice*, so members need not
                # re-register when switching days. Never touch live players.
                store.register(test_settings.season_key, p.discord_user_id,
                               p.mr_username, p.city, day_start - timedelta(minutes=1))
            store.transition(test_settings.season_key, host_id, "start", day_start,
                             f"Disposable Day {day} rehearsal")
            WorldEngine(store).tick(test_settings.season_key, now)
        except Exception:
            store.retire()
            self._erase_files(path)
            raise
        return PracticeSession(session_id, day, channel_id, test_settings, store, now)

    def start(self, day: int, channel_id: int, host_id: int, now: datetime) -> PracticeSession:
        with self._lock:
            if self._session is not None:
                raise PracticeError("A test is already running. End it or select another test day.")
            self._check_live(now)
            session = self._new(day, channel_id, host_id, now)
            self._session = session
            return session

    def change_day(self, day: int, host_id: int, now: datetime) -> PracticeSession:
        with self._lock:
            old = self._session
            if old is None:
                raise PracticeError("No active test. Use /snowadmin test-start first.")
            if day == old.day:
                return old
            self._check_live(now)
            registered = old.store.registrations(old.settings.season_key)
            fresh = self._new(day, old.channel_id, host_id, now, registered)
            old.store.retire()
            self._erase_files(old.store.path)
            self._session = fresh
            return fresh

    @staticmethod
    def _erase_files(path: Path) -> None:
        # Narrow deletion to the exact disposable session file and its WAL files.
        for suffix in ("", "-wal", "-shm", "-journal"):
            target = Path(str(path) + suffix)
            target.unlink(missing_ok=True)

    def end(self, *, archive: bool = False) -> Path | None:
        """Revoke all stale menu DB access; archive or delete this one session."""
        with self._lock:
            session = self._session
            if session is None:
                raise PracticeError("There is no active test day to end")
            archived = None
            if archive:
                self.archive_dir.mkdir(parents=True, exist_ok=True)
                archived = self.archive_dir / f"test-day-{session.day}-{session.id}.sqlite3"
                # SQLite online backup is a consistent WAL-aware snapshot.
                # If archiving fails, leave the practice session usable.
                try:
                    with session.store._lock:
                        with sqlite3.connect(session.store.path) as source:
                            with sqlite3.connect(archived) as target:
                                source.backup(target)
                                result = target.execute("PRAGMA quick_check").fetchone()[0]
                                if result != "ok":
                                    raise PracticeError(f"Archive verification failed: {result}")
                except Exception:
                    archived.unlink(missing_ok=True)
                    raise
            session.store.retire()
            self._session = None
            self._erase_files(session.store.path)
            return archived

    def snapshot(self, now: datetime) -> dict:
        with self._lock:
            session = self._session
            if not session:
                return {"active": False}
            players = session.store.registrations(session.settings.season_key)
            return {"active": True, "day": session.day,
                    "channel_id": session.channel_id,
                    "started_at": session.started_at_utc,
                    "players": len(players), "session_id": session.id,
                    "theme": THEMES[session.day - 1],
                    "bonus": DAY_DETAILS[session.day - 1][1]}

    def clean_orphans(self) -> int:
        """Old crashed practice DBs cannot be selected as current on boot."""
        self.practice_dir.mkdir(parents=True, exist_ok=True)
        total = 0
        for path in self.practice_dir.glob("day-*-*.sqlite3"):
            # Don't touch files outside the managed practice directory.
            if path.is_file() and path.resolve().parent == self.practice_dir.resolve():
                self._erase_files(path)
                total += 1
        return total


class ScopedSettings:
    def __init__(self, manager: PracticeManager):
        self.manager = manager

    def resolve(self):
        return self.manager.selected()[0]

    def __getattr__(self, name):
        return getattr(self.resolve(), name)


class ScopedStore:
    def __init__(self, manager: PracticeManager):
        self.manager = manager

    def resolve(self):
        return self.manager.selected()[1]

    def __getattr__(self, name):
        return getattr(self.resolve(), name)


def pin(settings, store):
    """Fix a view to its original season rather than routing future button clicks."""
    return (settings.resolve() if isinstance(settings, ScopedSettings) else settings,
            store.resolve() if isinstance(store, ScopedStore) else store)


def practice_expired(settings, store) -> bool:
    return getattr(settings, "mode", "production") == "practice" and not getattr(store, "active", False)
