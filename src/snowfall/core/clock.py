"""One authoritative UTC clock for registration and season-day math."""
from datetime import datetime, timedelta, timezone


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Time values must include a timezone")
    return value.astimezone(timezone.utc)


def registration_opens(start: datetime) -> datetime:
    return as_utc(start) - timedelta(days=7)


def event_ends(start: datetime) -> datetime:
    return as_utc(start) + timedelta(days=7)


def phase(start: datetime, now: datetime) -> str:
    """Pre-pause foundation: full pause/resume clock is a later ticket."""
    start, now = as_utc(start), as_utc(now)
    if now < registration_opens(start):
        return "not_open"
    if now < start:
        return "registration"
    if now < event_ends(start):
        return "live"
    return "closed"


def game_day(start: datetime, now: datetime) -> int | None:
    start, now = as_utc(start), as_utc(now)
    if not start <= now < event_ends(start):
        return None
    return (now - start).days + 1
