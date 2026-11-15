"""Pure scoring functions for later DB/ledger integration."""
from collections.abc import Sequence


def city_day_score(contributions: Sequence[int], siege_cleared: bool) -> float:
    """City score for registered eligible ACTIVE participants (not all signups)."""
    if any(n < 0 for n in contributions):
        raise ValueError("Contributions cannot be negative")
    if len(contributions) < 3:
        return 0.0
    top_five = sorted((min(300, n) for n in contributions), reverse=True)[:5]
    top_five.extend([0] * (5 - len(top_five)))
    participation = min(40, 4 * max(0, len(contributions) - 5))
    return sum(top_five) / 5 + participation + (25 if siege_cleared else 0)
