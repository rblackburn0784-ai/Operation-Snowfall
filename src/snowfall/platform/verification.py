"""v2.9.4e: Verifiable one-player, two-platform gameplay QA.

The web owner starts a 15-minute read-only baseline. Only a real Discord
interaction, resolved via the identity table, may acknowledge that baseline.
Actual Discord gameplay is proved by the canonical immutable event ledger,
not by a user claim or a mirrored score. Website gameplay is identifiable
by its 'web:' idempotency key. No test writes game points or inventory.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json

from snowfall.platform.identity import IdentityConflict, IdentityError

QA_SEASON = "web-qa-2026"
COLUMNS = ("score", "snowballs", "snowflakes", "warmth", "inventory", "boss_hp", "boss_max_hp")
EVENT_TABLES = (
    ("item_events", "discord_user_id", "happened_at_utc"),
    ("pve_events", "attacker_id", "happened_at_utc"),
    ("combat_events", "attacker_id", "happened_at_utc"),
)


def _values(snapshot):
    """Return stable, JSON-safe canonical player stats for a display comparison."""
    return {key: snapshot.get(key) for key in COLUMNS}


def _difference(before, after):
    result = {}
    for key in ("score", "snowballs", "snowflakes", "warmth", "boss_hp"):
        result[key] = int(after.get(key, 0)) - int(before.get(key, 0))
    inventory = {}
    for item in set(before.get("inventory") or {}) | set(after.get("inventory") or {}):
        delta = int((after.get("inventory") or {}).get(item, 0)) - int(
            (before.get("inventory") or {}).get(item, 0))
        if delta:
            inventory[item] = delta
    result["inventory"] = dict(sorted(inventory.items()))
    return result


class CrossPlatformVerifier:
    """QA-only, authoritative Postgres proof of account and gameplay sharing."""

    def __init__(self, identities, game, season: str):
        if season != QA_SEASON:
            raise IdentityError("Cross-platform verification is isolated-QA only")
        self.identities, self.game, self.season = identities, game, season

    def _snapshot(self, player_id):
        snapshot = self.game.progress(player_id)
        if not snapshot.get("registered"):
            raise IdentityConflict("Register your shared Snowfall character before verification")
        if snapshot.get("season") != self.season:
            raise IdentityConflict("Cannot compare different Snowfall seasons")
        return snapshot

    def _links(self, player_id):
        links = self.identities.links(player_id)
        if not ({x["provider"] for x in links} >= {"discord", "underworld"}):
            raise IdentityConflict("Link both Underworld and Discord before verification")
        return links

    def start(self, player_id: int):
        """Trusted authenticated web session calls this with CSRF enabled."""
        self._links(player_id)
        progress = self._snapshot(player_id)
        with self.identities._connect() as conn:
            conn.execute(
                """INSERT INTO snowfall_identity_platform_checks(
                    player_id, season_key, started_at, expires_at, baseline,
                    discord_seen_at, discord_snapshot)
                   VALUES(%s,%s,now(),now()+interval '15 minutes',%s::jsonb,NULL,NULL)
                   ON CONFLICT(player_id) DO UPDATE SET
                    season_key=EXCLUDED.season_key, started_at=EXCLUDED.started_at,
                    expires_at=EXCLUDED.expires_at, baseline=EXCLUDED.baseline,
                    discord_seen_at=NULL, discord_snapshot=NULL""",
                (player_id, self.season, json.dumps(progress)))
        return self.status(player_id)

    def from_discord(self, discord_user_id: int):
        """Only the gateway passes interaction.user.id, never a user-submitted ID."""
        principal = self.identities.principal_for_discord(str(discord_user_id))
        self._links(principal)
        progress = self._snapshot(principal)
        with self.identities._connect() as conn:
            result = conn.execute(
                """UPDATE snowfall_identity_platform_checks
                   SET discord_seen_at=now(), discord_snapshot=%s::jsonb
                   WHERE player_id=%s AND season_key=%s
                     AND expires_at>now() RETURNING player_id""",
                (json.dumps(progress), principal, self.season)).fetchone()
            if result is None:
                raise IdentityConflict(
                    "Start a 15-minute Cross-Platform Verification on Snowfall Web first")
        return self.status(principal)

    def _events(self, conn, player_id: int, since: datetime):
        """Count real authoritative events; never count an arbitrary fake assertion.

        The Discord engines use Discord's numeric interaction IDs or the
        discord-bridge: prefix. Website actions use the web: prefix. Records
        from other services or prior to the baseline are ignored.
        """
        categories = {"discord": {"count": 0, "last": None},
                      "web": {"count": 0, "last": None}}
        for table, player_column, time_column in EVENT_TABLES:
            for origin in categories:
                if origin == "discord":
                    condition = "(interaction_id LIKE %s OR interaction_id ~ %s)"
                    identifiers = ("discord-bridge:%", "^[0-9]{16,20}$")
                else:
                    condition = "interaction_id LIKE %s"
                    identifiers = ("web:%",)
                # All SQL identifiers are constants from EVENT_TABLES, never
                # user-controlled. Event timestamps come from authoritative
                # immutable history and are stored as UTC ISO text.
                sql = (f"SELECT COUNT(*), MAX({time_column}::timestamptz) "
                       f"FROM {table} WHERE season_key=%s AND {player_column}=%s "
                       f"AND {time_column}::timestamptz >= %s AND {condition}")
                count, latest = conn.execute(
                    sql, (self.season, player_id, since, *identifiers)).fetchone()
                categories[origin]["count"] += int(count)
                if latest is not None:
                    old = categories[origin]["last"]
                    categories[origin]["last"] = latest if old is None else max(old, latest)
        return categories

    def status(self, player_id: int):
        """Read-only proof and diff, grounded in the same canonical DB as web."""
        self._links(player_id)
        with self.identities._connect() as conn:
            row = conn.execute(
                """SELECT started_at,expires_at,baseline,discord_seen_at,discord_snapshot
                   FROM snowfall_identity_platform_checks WHERE player_id=%s
                     AND season_key=%s""", (player_id, self.season)).fetchone()
            if row is None:
                return {"state": "not_started", "player_id": str(player_id),
                        "discord_confirmed": False,
                        "discord_gameplay_verified": False,
                        "web_gameplay_seen_by_discord": False}
            started, expires, baseline, seen_at, discord_snapshot = row
            now = datetime.now(timezone.utc)
            if now >= expires:
                return {"state": "expired", "player_id": str(player_id),
                        "discord_confirmed": False,
                        "discord_gameplay_verified": False,
                        "web_gameplay_seen_by_discord": False}
            activity = self._events(conn, player_id, started)

        current = self._snapshot(player_id)
        discord_activity = activity["discord"]["count"]
        web_activity = activity["web"]["count"]
        web_visible = bool(seen_at and activity["web"]["last"] and
                           activity["web"]["last"] <= seen_at and discord_snapshot)
        return {
            "state": ("discord_gameplay_verified" if seen_at and discord_activity
                      else "discord_confirmed" if seen_at else "awaiting_discord"),
            "player_id": str(player_id),
            "season": self.season,
            "character": current["mr_username"],
            "started_at": started.isoformat(),
            "expires_at": expires.isoformat(),
            "discord_confirmed": seen_at is not None,
            "discord_gameplay_verified": bool(seen_at and discord_activity),
            "web_gameplay_seen_by_discord": web_visible,
            "discord_action_count": discord_activity,
            "web_action_count": web_activity,
            "baseline": _values(baseline),
            "discord_snapshot": _values(discord_snapshot) if discord_snapshot else None,
            "current": _values(current),
            "delta": _difference(baseline, current),
            "instructions": (
                "Use /snowbridge verify in Discord, then craft an item or attack "
                "Snow Don using /snow or /snowbridge. Refresh here to verify "
                "the authoritative Discord action. For the reverse direction, "
                "craft on the website, then use /snowbridge verify again."),
        }
