"""v0.2.8 Snowfall Wire newsroom, deterministic facts and moderated player stories.

Only wire_submissions may be written here. Score, city competition,
resources, combat, achievements and prizes are authoritative elsewhere.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import re
import unicodedata

from snowfall.core.clock import as_utc
from snowfall.db.store import Store, _timestamp
from snowfall.services.world import THEMES


class WireError(ValueError):
    """Invalid edition or unapproved editorial action."""


HEADLINES = (
    "THE FIRST SNOWBALL HAS LANDED",
    "FORTRESSES BRACE FOR THE FREEZE",
    "WHITEOUT SWEEPS THE SIX CITIES",
    "CHRISTMAS PARCELS IN THE CROSSFIRE",
    "THE SNOW DON ANSWERS BACK",
    "BLIZZARD BUSINESS HEATS UP",
    "ONE LAST ROUND IN THE SNOW",
)
OPENING = (
    "Chicago's alleys are white with snow, and the city crews are only getting started.",
    "From the frozen warehouse district, the morning dispatch has news from across six cities.",
    "A thick whiteout covers the streets. The Wire is still keeping an eye on the figures.",
    "The holiday supply routes are busy, and the bosses have their own plans.",
    "The Snow Don is back on the streets, and the reports keep coming.",
    "The city's windows are frosted; the ledgers are warmer than ever.",
    "Seven days, six cities, and one last edition from the underworld.",
)
MAX_STORIES = 2


@dataclass(frozen=True)
class PlayerStory:
    id: int
    day: int
    byline: str
    city: str
    headline: str
    story: str
    status: str


@dataclass(frozen=True)
class WireEdition:
    day: int
    completed: bool
    phase: str
    theme: str
    headline: str
    opening: str
    top_player: str | None
    top_city: str | None
    top_points: int
    busy_city: str | None
    busy_activity: int
    active_people: int
    throws: int
    hits: int
    largest_hit: int
    largest_hitter: str | None
    boss_damage: int
    sieges_cleared: int
    quests: int
    presents: int
    cases_solved: int
    arcade_runs: int
    stories: tuple[PlayerStory, ...]


def clean_name(raw: str, limit: int = 50) -> str:
    """Never interpret self-declared MR names or player-written copy as Discord."""
    value = " ".join(str(raw).split())[:limit]
    # Escape Markdown and disarm pings without discord.py dependency.
    for char in ("\\", "*", "_", "~", "`", "<", ">", "|"):
        value = value.replace(char, "")
    return value.replace("@", "＠") or "Unknown"


def _copy(raw: str) -> str:
    if not isinstance(raw, str):
        raise WireError("The story must contain plain text.")
    value = unicodedata.normalize("NFKC", raw).strip()
    if any(unicodedata.category(c).startswith("C") and c not in "\n\t" for c in value):
        raise WireError("Control characters are not allowed in the newspaper.")
    return " ".join(value.split())


def _eligible(con, season: str, user: int):
    row = con.execute(
        "SELECT mr_username,city,review_state FROM players WHERE "
        "season_key=? AND discord_user_id=?", (season, user)).fetchone()
    if row is None:
        raise WireError("Register with /snow join before submitting a story.")
    if row["review_state"] in ("flagged", "disqualified"):
        raise WireError("Your account is under identity review; submissions are unavailable.")
    return row


def _row_story(row) -> PlayerStory:
    return PlayerStory(int(row["id"]), int(row["day"]), row["mr_username"], row["city"],
                       row["headline"], row["story"], row["status"])


def _one(con, query: str, args=()):
    return int(con.execute(query, args).fetchone()[0] or 0)


class WireEngine:
    def __init__(self, store: Store):
        self.store = store

    def latest_day(self, season: str, now: datetime) -> int:
        state = self.store.season(season)
        if state.started_at is None or as_utc(now) < state.started_at:
            return 0
        elapsed = (state.effective_now(now) - state.started_at).total_seconds()
        return min(7, max(1, int(max(0, elapsed) // 86400) + 1))

    def edition(self, season: str, day: int, now: datetime) -> WireEdition:
        now = as_utc(now)
        state = self.store.season(season)
        last = self.latest_day(season, now)
        if not 1 <= day <= last:
            raise WireError("That newspaper edition has not opened yet.")
        completed = state.effective_now(now) >= state.started_at + timedelta(days=day)
        with self.store.connect() as con:
            con.execute("BEGIN")
            leader = con.execute("""SELECT p.mr_username,p.city,SUM(l.points) score
                FROM score_ledger l
                JOIN players p ON p.season_key=l.season_key
                    AND p.discord_user_id=l.player_id
                WHERE l.season_key=? AND l.day=? AND l.points>0
                    AND p.review_state NOT IN ('flagged','disqualified')
                GROUP BY l.player_id HAVING SUM(l.points)>0
                ORDER BY score DESC,p.mr_username_norm ASC LIMIT 1""",
                (season,day)).fetchone()
            city = con.execute("""SELECT p.city,COUNT(*) events
                FROM score_ledger l JOIN players p
                    ON p.season_key=l.season_key AND p.discord_user_id=l.player_id
                WHERE l.season_key=? AND l.day=? AND l.points>0
                  AND p.review_state NOT IN ('flagged','disqualified')
                GROUP BY p.city ORDER BY events DESC,p.city ASC LIMIT 1""",
                (season,day)).fetchone()
            people = _one(con, """SELECT COUNT(DISTINCT l.player_id)
                FROM score_ledger l JOIN players p
                    ON p.season_key=l.season_key AND p.discord_user_id=l.player_id
                WHERE l.season_key=? AND l.day=? AND l.points>0
                  AND p.review_state NOT IN ('flagged','disqualified')""",
                (season,day))
            throws,hits,largest = con.execute("""SELECT COUNT(*),
                    COALESCE(SUM(c.hit),0),
                    COALESCE(MAX(c.warmth_damage+c.armour_damage),0)
                FROM combat_events c JOIN players p
                    ON p.season_key=c.season_key AND p.discord_user_id=c.attacker_id
                WHERE c.season_key=? AND c.day=?
                    AND p.review_state NOT IN ('flagged','disqualified')""",
                (season,day)).fetchone()
            hitter = con.execute("""SELECT p.mr_username FROM combat_events c
                    JOIN players p ON p.season_key=c.season_key
                    AND p.discord_user_id=c.attacker_id
                WHERE c.season_key=? AND c.day=?
                    AND c.warmth_damage+c.armour_damage=?
                    AND p.review_state NOT IN ('flagged','disqualified')
                ORDER BY c.id ASC LIMIT 1""", (season,day,largest)).fetchone() if largest else None
            damage = _one(con, """SELECT COALESCE(SUM(e.damage),0)
                FROM pve_events e JOIN players p ON p.season_key=e.season_key
                    AND p.discord_user_id=e.attacker_id
                WHERE e.season_key=? AND e.day=? AND e.kind='boss' AND e.echo=0
                    AND p.review_state NOT IN ('flagged','disqualified')""",
                (season,day))
            forts = _one(con,"SELECT COUNT(*) FROM world_sieges WHERE "
                         "season_key=? AND day=? AND cleared_at_utc IS NOT NULL",(season,day))
            quests = _one(con, """SELECT COUNT(*) FROM quest_claims q JOIN players p
                    ON p.season_key=q.season_key AND p.discord_user_id=q.discord_user_id
                WHERE q.season_key=? AND q.day=?
                    AND p.review_state NOT IN ('flagged','disqualified')""",
                (season,day))
            gifts = _one(con, """SELECT COUNT(*) FROM mystery_gifts m JOIN players p
                    ON p.season_key=m.season_key AND p.discord_user_id=m.discord_user_id
                WHERE m.season_key=? AND m.day=?
                    AND p.review_state NOT IN ('flagged','disqualified')""",
                (season,day))
            solved = _one(con, """SELECT COUNT(*) FROM mystery_guesses g JOIN players p
                    ON p.season_key=g.season_key AND p.discord_user_id=g.discord_user_id
                WHERE g.season_key=? AND g.day=? AND g.correct=1
                    AND p.review_state NOT IN ('flagged','disqualified')""",
                (season,day))
            arcade = _one(con, """SELECT COUNT(*) FROM social_arcade_runs r JOIN players p
                    ON p.season_key=r.season_key AND p.discord_user_id=r.discord_user_id
                WHERE r.season_key=? AND r.day=? AND r.status='finished'
                    AND p.review_state NOT IN ('flagged','disqualified')""",
                (season,day))
            approved = con.execute("""SELECT w.*,p.mr_username,p.city
                FROM wire_submissions w JOIN players p
                    ON p.season_key=w.season_key AND p.discord_user_id=w.discord_user_id
                WHERE w.season_key=? AND w.day=? AND w.status='approved'
                    AND p.review_state NOT IN ('flagged','disqualified')
                ORDER BY w.id ASC LIMIT ?""",(season,day,MAX_STORIES)).fetchall()
        return WireEdition(
            day,completed,state.phase(now),THEMES[day-1],HEADLINES[day-1],OPENING[day-1],
            leader["mr_username"] if leader else None,leader["city"] if leader else None,
            int(leader["score"]) if leader else 0,
            city["city"] if city else None,int(city["events"]) if city else 0,
            people,int(throws),int(hits),int(largest),
            hitter["mr_username"] if hitter else None,damage,forts,quests,gifts,
            solved,arcade,tuple(_row_story(row) for row in approved))

    def submit(self, season: str, user: int, headline: str, story: str,
               now: datetime) -> PlayerStory:
        headline = _copy(headline)
        story = _copy(story)
        if not 8 <= len(headline) <= 76:
            raise WireError("A headline must contain 8–76 characters.")
        if not 40 <= len(story) <= 500:
            raise WireError("The story must contain 40–500 characters.")
        if re.search(r"(?:https?://|discord\.gg/|@everyone|@here)",headline+" "+story,re.I):
            raise WireError("No links or Discord-wide pings are permitted in player stories.")
        now = as_utc(now)
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            _eligible(con,season,user)
            state = self.store.season(season)
            if state.phase(now)!="live":
                raise WireError("Submissions open only during live event days.")
            day=state.day(now)
            prev=con.execute("SELECT w.*,p.mr_username,p.city FROM wire_submissions w "
                             "JOIN players p ON p.season_key=w.season_key "
                             "AND p.discord_user_id=w.discord_user_id "
                             "WHERE w.season_key=? AND w.discord_user_id=? AND w.day=?",
                             (season,user,day)).fetchone()
            if prev:
                if prev["headline"]==headline and prev["story"]==story:
                    return _row_story(prev)
                raise WireError("Your story for this day has already been submitted.")
            con.execute("""INSERT INTO wire_submissions(
                season_key,discord_user_id,day,headline,story,submitted_at_utc)
                VALUES(?,?,?,?,?,?)""",(season,user,day,headline,story,_timestamp(now)))
            row=con.execute("SELECT w.*,p.mr_username,p.city FROM wire_submissions w "
                            "JOIN players p ON p.season_key=w.season_key "
                            "AND p.discord_user_id=w.discord_user_id "
                            "WHERE w.season_key=? AND w.discord_user_id=? AND w.day=?",
                            (season,user,day)).fetchone()
            return _row_story(row)

    def my_story(self, season: str, user: int, now: datetime):
        with self.store.connect() as con:
            _eligible(con,season,user)
            row=con.execute("SELECT w.*,p.mr_username,p.city FROM wire_submissions w "
                            "JOIN players p ON p.season_key=w.season_key "
                            "AND p.discord_user_id=w.discord_user_id "
                            "WHERE w.season_key=? AND w.discord_user_id=? "
                            "ORDER BY w.day DESC LIMIT 1",(season,user)).fetchone()
            return _row_story(row) if row else None

    def queue(self, season: str, *, day: int | None = None,
              status: str = "pending") -> tuple[PlayerStory,...]:
        if status not in ("pending","approved","rejected"):
            raise WireError("Invalid editorial queue filter.")
        if day is not None and not 1 <= day <= 7:
            raise WireError("Day must be between 1 and 7.")
        with self.store.connect() as con:
            rows=con.execute("""SELECT w.*,p.mr_username,p.city
                FROM wire_submissions w JOIN players p ON p.season_key=w.season_key
                  AND p.discord_user_id=w.discord_user_id
                WHERE w.season_key=? AND w.status=?
                """+(" AND w.day=?" if day is not None else "")+
                " ORDER BY w.id DESC LIMIT 30",
                (season,status,day) if day is not None else (season,status)).fetchall()
        return tuple(_row_story(r) for r in rows)

    def review(self, season: str, submission_id: int, decision: str, actor: int,
               host_ids: frozenset[int], now: datetime) -> PlayerStory:
        if actor not in host_ids:
            raise WireError("Only a configured event host may review player stories.")
        if decision not in ("approved","rejected"):
            raise WireError("Choose approved or rejected.")
        if not isinstance(submission_id,int) or submission_id <= 0:
            raise WireError("Provide a valid story ID from the editorial queue.")
        now=as_utc(now)
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row=con.execute("SELECT * FROM wire_submissions WHERE season_key=? AND id=?",
                            (season,submission_id)).fetchone()
            if row is None:
                raise WireError("Story not found in this season.")
            if row["status"] != "pending":
                raise WireError("This story has already received an editorial decision.")
            author=_eligible(con,season,int(row["discord_user_id"]))
            con.execute("UPDATE wire_submissions SET status=?,reviewed_by=?,"
                        "reviewed_at_utc=? WHERE id=?",
                        (decision,actor,_timestamp(now),submission_id))
            final=con.execute("SELECT * FROM wire_submissions WHERE id=?",
                              (submission_id,)).fetchone()
        return PlayerStory(int(final["id"]),int(final["day"]),author["mr_username"],
                           author["city"],final["headline"],final["story"],final["status"])

    def flash(self, season: str, now: datetime) -> tuple[int,str] | None:
        """One notable in-world event per day, never invented and never paid."""
        state=self.store.season(season)
        day=state.day(now)
        if day is None or state.phase(now)!="live":
            return None
        edition=self.edition(season,day,now)
        if edition.throws >= 10:
            return day, (f"🗞️ **SNOWFALL WIRE — STREET FLASH, DAY {day}/7**\n"
                         f"Ten or more recorded snowballs have crossed the streets "
                         f"today. The count now stands at **{edition.throws} throws** "
                         f"and **{edition.hits} hits**.\n"
                         "*Automatic factual community bulletin. No prizes or bonuses.*")
        if edition.arcade_runs >= 12:
            return day, (f"🗞️ **SNOWFALL WIRE — ARCADE FLASH, DAY {day}/7**\n"
                         f"Players have finished **{edition.arcade_runs} Winter Arcade "
                         f"runs** today. The speakeasy machines are busy.\n"
                         "*Casual games only. No additional prizes.*")
        return None


def edition_text(edition: WireEdition, *, practice: bool=False) -> str:
    mast="🧪 **SNOWFALL WIRE / TEST EDITION**" if practice else "🗞️ **THE SNOWFALL WIRE 2.0**"
    parts=[mast,f"**{edition.headline}**",
           f"**DAY {edition.day}/7** · {edition.theme} · "
           + ("Morning Edition" if edition.completed else "Live Street Edition") + "*",
           edition.opening]
    if edition.top_player:
        parts.append(f"🏆 **TOP OF THE RACKET:** {clean_name(edition.top_player)} "
                     f"({clean_name(edition.top_city)}) has {edition.top_points} "
                     "recorded daily points.")
    else:
        parts.append("🏆 **TOP OF THE RACKET:** No eligible points recorded yet.")
    if edition.busy_city:
        parts.append(f"🏙️ **BUSIEST STREETS:** {clean_name(edition.busy_city)} "
                     f"recorded {edition.busy_activity} positive scoring entries "
                     "in the daily ledger. This is activity, not an official city rank.")
    else:
        parts.append("🏙️ **BUSIEST STREETS:** No city qualified for the daily activity tally yet.")
    parts.append(f"🎯 **THE STREET LEDGER:** {edition.active_people} participants, "
                 f"{edition.throws} throws, {edition.hits} hits"
                 + (f"; best strike {edition.largest_hit} by "
                    f"{clean_name(edition.largest_hitter)}" if edition.largest_hitter else "") + ".")
    parts.append(f"☃️ **THE DON'S DESK:** {edition.boss_damage} genuine boss damage; "
                 f"{edition.sieges_cleared} city sieges cleared.")
    parts.append(f"🎁 **BACKROOM NOTES:** {edition.quests} quests, {edition.presents} gifts, "
                 f"{edition.cases_solved} solved detective cases, "
                 f"{edition.arcade_runs} finished arcade games.")
    for story in edition.stories:
        parts.append(f"📝 **PLAYER DISPATCH — {clean_name(story.headline,76)}**\n"
                     f"*By {clean_name(story.byline,32)}, {clean_name(story.city,32)} "
                     "(opt-in and host-approved)*\n"
                     + clean_name(story.story,200))
    parts.append("*Fictional in-game newspaper; statistics use recorded events. "
                 "Player dispatches are attributed opinions or fiction, not verified facts. "
                 "All prizes remain individual only.*")
    return "\n".join(parts)[:1900]
