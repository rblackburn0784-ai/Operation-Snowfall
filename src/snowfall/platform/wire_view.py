"""Read-only verified newspaper editions for the isolated web presentation."""
from dataclasses import asdict
from datetime import datetime, timezone

from snowfall.services.community import CommunityEngine
from snowfall.services.wire import WireEngine, WireError
from snowfall.services.world import THEMES


def wire_view(game, day=None, now=None):
    """Publish verified ledger headlines, not private editorial submissions."""
    now = now or datetime.now(timezone.utc)
    state = game.store.season(game.season)
    if state is None:
        raise WireError("Season is not configured.")
    phase = state.phase(now)
    current = state.day(now)
    completed = CommunityEngine(game.store).latest_completed_day(game.season, now)
    available = max(current or 0, completed)
    if day is not None and not 1 <= day <= min(7, available):
        raise WireError("That edition has not opened yet.")
    selected = day if day is not None else (available or None)
    return {
        "phase": phase, "current_day": current, "last_completed": completed,
        "available_days": list(range(1, min(7, available) + 1)),
        "day": selected,
        "complete": selected is not None and selected <= completed,
        "theme": THEMES[selected - 1] if selected is not None else "Awaiting kickoff",
        "headlines": [asdict(h) for h in WireEngine(game.store).headlines(game.season, selected)]
        if selected is not None else [],
        "server_time": now,
        "projected_end": state.projected_end(now),
        "verified_only": True,
    }
