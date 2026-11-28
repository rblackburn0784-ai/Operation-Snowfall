"""Opt-in QA-only replacement of an owned Discord profile with an Underworld player.

This is NOT a score/asset merge. Once both account providers are verified
through Underworld session + Discord OAuth, a separate confirmation can retire
the Discord-only game character and link its login to Underworld. Immutable
gameplay history is retained for audit, NOT deleted or transferred.
"""
from __future__ import annotations

from hashlib import sha256
import secrets

from snowfall.db.migrate_postgres import EXPECTED_TABLES
from snowfall.db.postgres import LOCK_KEY as GAME_LOCK
from snowfall.platform.identity import IdentityConflict, IdentityError, LOCK, PLAYER_START, digest

QA_SEASON = "web-qa-2026"
CONFIRM_PHRASE = "DISCARD DISCORD CHARACTER"
OWNER_COLUMNS = frozenset({
    "discord_user_id", "player_id", "user_id", "attacker_id", "target_id",
    "defender_id", "actor_id", "subject_id", "winner_id", "owner_id",
    "opponent_id", "host_id", "moderator_id",
})


class DiscardService:
    """Server-side challenge and atomic transaction; no user-supplied player IDs."""

    def __init__(self, identities, season: str):
        self.identities = identities
        if season != QA_SEASON:
            raise IdentityError("Discarding an account is only enabled in isolated QA")
        self.season = season

    @staticmethod
    def _locks(cur):
        # Identity before gameplay: same lock ordering as identity.link_discord().
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (GAME_LOCK,))

    def _eligible(self, cur, target_id: int, discord_subject: str):
        """Fail closed for any other Underworld or Discord-account linkage."""
        if not discord_subject.isdecimal() or not 0 < int(discord_subject) < PLAYER_START:
            raise IdentityConflict("Invalid verified Discord identity")
        original = int(discord_subject)
        if original == target_id:
            raise IdentityConflict("Discord is already the selected character")
        cur.execute("""SELECT 1 FROM snowfall_identity_links
                       WHERE provider='underworld' AND player_id=%s LIMIT 1""", (target_id,))
        if not cur.fetchone():
            raise IdentityConflict("Sign in through Underworld to choose the saved character")
        cur.execute("""SELECT subject FROM snowfall_identity_links
                       WHERE provider='discord' AND player_id=%s""", (target_id,))
        if cur.fetchone():
            raise IdentityConflict("Underworld character already has a Discord account linked")
        cur.execute("""SELECT player_id FROM snowfall_identity_links
                       WHERE provider='discord' AND subject=%s""", (discord_subject,))
        linked = cur.fetchone()
        if not linked or int(linked[0]) != original:
            raise IdentityConflict("Discord account is not a separate Discord-only character")
        cur.execute("SELECT provider FROM snowfall_identity_links WHERE player_id=%s",
                    (original,))
        if [x[0] for x in cur.fetchall()] != ["discord"]:
            raise IdentityConflict("Discord character has another linked identity")
        cur.execute("""SELECT mr_username,city,review_state FROM players
                       WHERE season_key=%s AND discord_user_id=%s""",
                    (self.season, original))
        old = cur.fetchone()
        if not old or old[2] == "disqualified":
            raise IdentityConflict("Discord character is not eligible for retirement")
        cur.execute("""SELECT 1 FROM prize_awards
                       WHERE season_key=%s AND discord_user_id=%s LIMIT 1""",
                    (self.season, original))
        if cur.fetchone():
            raise IdentityConflict("Discord character has a prize award requiring staff review")
        cur.execute("""SELECT finalized_at_utc FROM season_state WHERE season_key=%s""",
                    (self.season,))
        state = cur.fetchone()
        if not state or state[0] is not None:
            raise IdentityConflict("Finalised event results cannot be changed")
        return original, old

    def _snapshot(self, cur, original: int) -> str:
        """Content fingerprint of ALL public game records referring to the old ID.

        Invalidates consent if points, inventory, actions or incoming attacks
        change between the preview and the irreversible confirmation.
        """
        from psycopg import sql  # Optional PostgreSQL extra: only required in QA runtime.
        cur.execute("""SELECT table_name,column_name FROM information_schema.columns
                       WHERE table_schema='public'
                         AND table_name NOT LIKE 'snowfall_identity_%%'
                         AND column_name = ANY(%s)
                       ORDER BY table_name,column_name""",
                    (sorted(OWNER_COLUMNS),))
        groups = {}
        for table, column in cur.fetchall():
            if table not in EXPECTED_TABLES and table not in {"snowfall_web_qa_bonus", "web_adventure_progress"}:
                raise IdentityConflict("Unknown player data table; staff review required")
            groups.setdefault(table, []).append(column)

        result = sha256()
        for table, columns in sorted(groups.items()):
            clause = sql.SQL(" OR ").join(
                sql.SQL("{}=%s").format(sql.Identifier(c)) for c in columns)
            statement = sql.SQL("SELECT to_jsonb(t)::text FROM {} t WHERE (").format(
                sql.Identifier(table)) + clause + sql.SQL(")")
            cur.execute(statement, (original,) * len(columns))
            rows = sorted(record[0] for record in cur.fetchall())
            result.update(table.encode())
            result.update(b"\0")
            for value in rows:
                result.update(value.encode())
                result.update(b"\n")
        return result.hexdigest()

    def _preview(self, cur, target_id: int, discord_subject: str):
        original, old = self._eligible(cur, target_id, discord_subject)
        cur.execute("""SELECT mr_username,city FROM players
                       WHERE season_key=%s AND discord_user_id=%s""",
                    (self.season, target_id))
        target = cur.fetchone()
        cur.execute("""SELECT COALESCE(SUM(points),0) FROM score_ledger
                       WHERE season_key=%s AND player_id=%s""",
                    (self.season, original))
        points = int(cur.fetchone()[0])
        cur.execute("""SELECT snowballs,warmth,snowflakes FROM player_resources
                       WHERE season_key=%s AND discord_user_id=%s""",
                    (self.season, original))
        resources = cur.fetchone() or (0, 100, 0)
        cur.execute("""SELECT item_key,quantity FROM player_inventory
                       WHERE season_key=%s AND discord_user_id=%s ORDER BY item_key""",
                    (self.season, original))
        inventory = {key: qty for key, qty in cur.fetchall() if qty > 0}
        cur.execute("""SELECT COUNT(*) FROM cosmetic_unlocks
                       WHERE season_key=%s AND discord_user_id=%s""",
                    (self.season, original))
        cosmetics = int(cur.fetchone()[0])
        cur.execute("""SELECT COUNT(*) FROM combat_events
                       WHERE season_key=%s AND attacker_id=%s""",
                    (self.season, original))
        attacks = int(cur.fetchone()[0])
        cur.execute("""SELECT COUNT(*) FROM pve_events
                       WHERE season_key=%s AND attacker_id=%s""",
                    (self.season, original))
        boss_attacks = int(cur.fetchone()[0])
        return {
            "keep": {"name": target[0] if target else "Unregistered Underworld character",
                     "city": target[1] if target else None,
                     "player_id": str(target_id)},
            "discard": {"name": old[0], "city": old[1],
                        "score": points, "snowflakes": int(resources[2]),
                        "snowballs": int(resources[0]), "warmth": int(resources[1]),
                        "inventory": inventory, "cosmetic_unlocks": cosmetics,
                        "pvp_attacks": attacks, "boss_attacks": boss_attacks},
            "warning": ("This permanently retires the Discord-only game character. "
                        "Its points, snowflakes, items, cosmetics, achievements and "
                        "game progress will NOT move to the Underworld character. "
                        "Historical game records are retained for audit and shared "
                        "world effects are not undone. There is no automatic undo."),
        }

    def begin(self, target_id: int, discord_subject: str, session_token: str) -> str:
        """Called only after Discord /users/@me and Underworld session verification."""
        if not session_token:
            raise IdentityError("Underworld browser session required")
        challenge = secrets.token_urlsafe(36)
        with self.identities._connect() as conn:
            with conn.cursor() as cur:
                self._locks(cur)
                self._eligible(cur, target_id, discord_subject)
                fingerprint = self._snapshot(cur, int(discord_subject))
                cur.execute("""DELETE FROM snowfall_identity_discard_intents
                               WHERE session_hash=%s""", (digest(session_token),))
                cur.execute("""INSERT INTO snowfall_identity_discard_intents
                               (challenge_hash,session_hash,target_player_id,
                                discord_subject,season_key,snapshot_hash,expires_at)
                               VALUES(%s,%s,%s,%s,%s,%s,now()+interval '10 minutes')""",
                            (digest("discard:" + challenge), digest(session_token),
                             target_id, discord_subject, self.season, fingerprint))
        return challenge

    def preview(self, target_id: int, session_token: str, challenge: str):
        if not challenge or not session_token:
            raise IdentityError("Expired Discord discard confirmation")
        with self.identities._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT target_player_id,discord_subject,snapshot_hash
                               FROM snowfall_identity_discard_intents
                               WHERE challenge_hash=%s AND session_hash=%s
                                 AND season_key=%s AND expires_at>now()""",
                            (digest("discard:" + challenge), digest(session_token),
                             self.season))
                row = cur.fetchone()
                if row is None or int(row[0]) != target_id:
                    raise IdentityError("Expired Discord discard confirmation")
                return self._preview(cur, target_id, row[1])

    def confirm(self, target_id: int, session_token: str, challenge: str,
                *, acknowledged: bool, phrase: str):
        if not acknowledged or phrase != CONFIRM_PHRASE:
            raise IdentityConflict("Tick the loss acknowledgement and type the exact phrase")
        if not challenge or not session_token:
            raise IdentityError("Expired discard confirmation; verify Discord again")

        with self.identities._connect() as conn:
            with conn.cursor() as cur:
                self._locks(cur)
                cur.execute("""SELECT target_player_id,discord_subject,snapshot_hash
                               FROM snowfall_identity_discard_intents
                               WHERE challenge_hash=%s AND session_hash=%s
                                 AND season_key=%s AND expires_at>now() FOR UPDATE""",
                            (digest("discard:" + challenge), digest(session_token),
                             self.season))
                row = cur.fetchone()
                if row is None or int(row[0]) != target_id:
                    raise IdentityError("Discard confirmation expired or already used")
                discord_subject, saved_fingerprint = row[1:]
                preview = self._preview(cur, target_id, discord_subject)
                old_id = int(discord_subject)
                if not secrets.compare_digest(
                        saved_fingerprint, self._snapshot(cur, old_id)):
                    raise IdentityConflict(
                        "Discord profile changed since preview; verify Discord again")

                # Keep immutable event, ledger, award, historical raid and audit
                # rows intact. Disqualified players are excluded from active
                # leaderboards and city standings by the official game engine.
                # Reclaiming the nickname avoids preventing the chosen
                # Underworld player from using it later.
                retired_name = "Retired-" + discord_subject
                cur.execute("""UPDATE players SET review_state='disqualified',
                               mr_username=%s,mr_username_norm=%s
                               WHERE season_key=%s AND discord_user_id=%s
                                 AND review_state!='disqualified'""",
                            (retired_name, retired_name.lower(), self.season, old_id))
                if cur.rowcount != 1:
                    raise IdentityConflict("Discord profile changed during retirement")
                cur.execute("""DELETE FROM snowfall_identity_sessions
                               WHERE player_id=%s""", (old_id,))
                cur.execute("""UPDATE snowfall_identity_links SET player_id=%s
                               WHERE provider='discord' AND subject=%s AND player_id=%s""",
                            (target_id, discord_subject, old_id))
                if cur.rowcount != 1:
                    raise IdentityConflict("Discord link changed during confirmation")
                cur.execute("""INSERT INTO snowfall_identity_discard_audit
                               (old_player_id,target_player_id,old_character_name,
                                season_key,points_discarded,snapshot_hash)
                               VALUES(%s,%s,%s,%s,%s,%s)""",
                            (old_id, target_id, preview["discard"]["name"],
                             self.season, preview["discard"]["score"],
                             saved_fingerprint))
                cur.execute("""DELETE FROM snowfall_identity_principals WHERE player_id=%s""",
                            (old_id,))
                cur.execute("""DELETE FROM snowfall_identity_discard_intents
                               WHERE challenge_hash=%s""",
                            (digest("discard:" + challenge),))
                return {"linked": True, "kept_player_id": str(target_id),
                        "retired_character": preview["discard"]["name"],
                        "discarded_points": preview["discard"]["score"]}

    def cancel(self, target_id: int, session_token: str, challenge: str) -> None:
        if not session_token or not challenge:
            return
        with self.identities._connect() as conn:
            conn.execute("""DELETE FROM snowfall_identity_discard_intents
                            WHERE challenge_hash=%s AND session_hash=%s
                              AND target_player_id=%s""",
                         (digest("discard:" + challenge), digest(session_token),
                          target_id))
