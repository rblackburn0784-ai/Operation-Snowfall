"""Snowfall Wire 2.0: verified newsroom facts and opt-in moderated fiction.

The verified newsroom derives from existing immutable event ledgers. Player
submissions are labelled as roleplay, held privately until a configured host
approves them, and never count as verified facts or game achievements.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import re

from snowfall.core.clock import as_utc
from snowfall.db.store import Store, _timestamp
from snowfall.services.community import CommunityEngine, wire_story, _safe_name
from snowfall.services.world import THEMES


class WireError(ValueError):
    pass


@dataclass(frozen=True)
class Headline:
    key: str
    title: str
    detail: str
    category: str


@dataclass(frozen=True)
class Story:
    id: int
    day: int
    author: str
    city: str
    title: str
    body: str
    status: str


@dataclass(frozen=True)
class Edition:
    day: int
    theme: str
    complete: bool
    headline: str
    verified: tuple[Headline, ...]
    report_text: str
    stories: tuple[Story, ...]


@dataclass(frozen=True)
class Newsroom:
    phase: str
    day: int | None
    last_completed: int
    recent: tuple[Headline, ...]
    approved_stories: int
    pending_stories: int
    my_story: Story | None


def _clean_text(raw: str, *, limit: int) -> str:
    """Single-line or paragraph narrative, no mass pings or Discord formatting."""
    if not isinstance(raw, str):
        raise WireError("Story text must be plain text.")
    value = " ".join(raw.strip().split())[:limit]
    value = value.replace("@", "＠").replace("<", "‹").replace(">", "›")
    value = re.sub(r"[*_`~\\]", "", value)
    return value


def _headline(key, title, detail, category):
    return Headline(key, title, detail, category)


class WireEngine:
    def __init__(self, store: Store):
        self.store = store

    def _reader(self, con, season, viewer):
        player = con.execute(
            "SELECT mr_username,city,review_state FROM players WHERE "
            "season_key=? AND discord_user_id=?", (season,viewer)).fetchone()
        if not player:
            raise WireError("Register first to access the Snowfall Wire.")
        if player["review_state"] in ("flagged", "disqualified"):
            raise WireError("The Wire is unavailable during identity review.")
        return player

    @staticmethod
    def _day(state, now):
        return state.day(now)

    @staticmethod
    def _story(row) -> Story:
        return Story(int(row["id"]), int(row["day"]), row["mr_username"],
                     row["city"], row["title"], row["body"], row["status"])

    def _stories(self, con, season, *, day=None, status="approved", limit=12):
        clause = " AND s.day=?" if day is not None else ""
        params = (season,day) if day is not None else (season,)
        where = (" AND d.verdict='approved'" if status=="approved" else
                 " AND d.verdict='rejected'" if status=="rejected" else
                 " AND d.submission_id IS NULL" if status=="pending" else "")
        rows = con.execute(f"""SELECT s.id,s.day,s.title,s.body,p.mr_username,p.city,
               COALESCE(d.verdict,'pending') status FROM wire_submissions s
               JOIN players p ON p.season_key=s.season_key
                 AND p.discord_user_id=s.discord_user_id
               LEFT JOIN wire_decisions d ON d.submission_id=s.id
               WHERE s.season_key=? {clause} {where}
                 AND p.review_state NOT IN ('flagged','disqualified')
               ORDER BY s.day DESC,s.id ASC LIMIT ?""",(*params,limit)).fetchall()
        return tuple(self._story(r) for r in rows)

    def stories(self, season: str, viewer: int, now: datetime, *,
                day: int | None = None) -> tuple[Story,...]:
        now=as_utc(now)
        with self.store.connect() as con:
            self._reader(con,season,viewer)
            if day is not None and not 1<=day<=7:
                raise WireError("Day must be between 1 and 7.")
            return self._stories(con,season,day=day)

    def public_stories(self, season: str, day: int) -> tuple[Story, ...]:
        """Only approved and currently eligible stories for automated broadcasts."""
        if not 1 <= day <= 7:
            raise WireError("Invalid Wire day.")
        with self.store.connect() as con:
            return self._stories(con,season,day=day)

    def pending(self, season: str, moderator: int, now: datetime, *,
                hosts: frozenset[int]) -> tuple[Story,...]:
        if moderator not in hosts:
            raise WireError("Only configured hosts can review community stories.")
        with self.store.connect() as con:
            return self._stories(con,season,status="pending")

    def submit(self, season: str, user: int, interaction_id: str,
               title: str, body: str, now: datetime) -> Story:
        if not isinstance(interaction_id,str) or not 1<=len(interaction_id)<=128:
            raise WireError("A unique Discord interaction ID is required.")
        title=_clean_text(title,limit=80)
        body=_clean_text(body,limit=650)
        if not 6<=len(title)<=80 or not 20<=len(body)<=650:
            raise WireError("Use a 6–80 character title and a 20–650 character story.")
        if re.search(r"(?i)https?://|discord\.gg/|<@|@everyone|@here",title+" "+body):
            raise WireError("Community stories cannot contain external links or mass mentions.")
        now=as_utc(now)
        state=self.store.season(season)
        if state.phase(now)!="live" or state.day(now) is None:
            raise WireError("Story submissions open during live event days only.")
        day=state.day(now)
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            self._reader(con,season,user)
            prior=con.execute("SELECT s.id,s.day,s.title,s.body,p.mr_username,p.city,"
                              "'pending' status FROM wire_submissions s JOIN players p "
                              "ON p.season_key=s.season_key AND "
                              "p.discord_user_id=s.discord_user_id "
                              "WHERE s.interaction_id=?",(interaction_id,)).fetchone()
            if prior:
                if (prior["day"]!=day or prior["title"]!=title or prior["body"]!=body or
                    con.execute("SELECT season_key,discord_user_id FROM wire_submissions "
                                "WHERE id=?",(prior["id"],)).fetchone()[:]!=(season,user)):
                    raise WireError("This interaction belongs to another submission.")
                return self._story(prior)
            existing=con.execute("SELECT id FROM wire_submissions WHERE season_key=? "
                                 "AND discord_user_id=? AND day=?",
                                 (season,user,day)).fetchone()
            if existing:
                raise WireError("One submitted story per player per day. "
                                "Your existing story is still saved for host review.")
            cursor=con.execute("INSERT INTO wire_submissions("
                               "interaction_id,season_key,discord_user_id,day,"
                               "title,body,created_at_utc) VALUES(?,?,?,?,?,?,?)",
                               (interaction_id,season,user,day,title,body,_timestamp(now)))
            player=con.execute("SELECT mr_username,city FROM players WHERE "
                               "season_key=? AND discord_user_id=?",(season,user)).fetchone()
            return Story(cursor.lastrowid,day,player["mr_username"],player["city"],
                         title,body,"pending")

    def decide(self, season: str, moderator: int, story_id: int,
               verdict: str, now: datetime, *, hosts: frozenset[int]) -> Story:
        if moderator not in hosts:
            raise WireError("Only configured hosts can moderate Wire submissions.")
        if verdict not in ("approved","rejected"):
            raise WireError("Invalid editorial decision.")
        now=as_utc(now)
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row=con.execute("""SELECT s.id,s.day,s.title,s.body,p.mr_username,p.city,
                    p.review_state,d.verdict status FROM wire_submissions s
                    JOIN players p ON p.season_key=s.season_key
                        AND p.discord_user_id=s.discord_user_id
                    LEFT JOIN wire_decisions d ON d.submission_id=s.id
                    WHERE s.season_key=? AND s.id=?""",(season,story_id)).fetchone()
            if not row:
                raise WireError("No such story in this season.")
            if row["review_state"] in ("flagged","disqualified"):
                raise WireError("Cannot approve a story from a reviewed identity.")
            if row["status"] is not None:
                if row["status"]!=verdict:
                    raise WireError("This story has already received a different decision.")
                return Story(int(row["id"]),int(row["day"]),row["mr_username"],
                             row["city"],row["title"],row["body"],verdict)
            con.execute("INSERT INTO wire_decisions("
                        "submission_id,season_key,moderator_id,verdict,reason,decided_at_utc) "
                        "VALUES(?,?,?,?,?,?)",(story_id,season,moderator,verdict,
                        "Editorial review — roleplay only",_timestamp(now)))
            return Story(int(row["id"]),int(row["day"]),row["mr_username"],
                         row["city"],row["title"],row["body"],verdict)

    def headlines(self, season: str, day: int) -> tuple[Headline,...]:
        if not 1<=day<=7:
            raise WireError("Invalid newspaper day.")
        with self.store.connect() as con:
            top=con.execute("""SELECT p.mr_username,p.city,SUM(l.points) points
                    FROM score_ledger l JOIN players p ON p.season_key=l.season_key
                      AND p.discord_user_id=l.player_id
                    WHERE l.season_key=? AND l.day=?
                      AND p.review_state NOT IN ('flagged','disqualified')
                    GROUP BY l.player_id HAVING SUM(l.points)>0
                    ORDER BY points DESC,p.mr_username_norm ASC LIMIT 1""",
                    (season,day)).fetchone()
            hits=con.execute("""SELECT COUNT(*) attempts,COALESCE(SUM(c.hit),0) hits,
                COALESCE(SUM(c.knocked_out),0) kos
                FROM combat_events c JOIN players p ON p.season_key=c.season_key
                AND p.discord_user_id=c.attacker_id
                WHERE c.season_key=? AND c.day=?
                AND p.review_state NOT IN ('flagged','disqualified')""",
                (season,day)).fetchone()
            boss=con.execute("""SELECT COALESCE(SUM(e.damage),0) damage,
                       COUNT(DISTINCT e.attacker_id) raiders FROM pve_events e
                JOIN players p ON p.season_key=e.season_key
                  AND p.discord_user_id=e.attacker_id
                WHERE e.season_key=? AND e.day=? AND e.kind='boss' AND e.echo=0
                AND p.review_state NOT IN ('flagged','disqualified')""",
                (season,day)).fetchone()
            forts=con.execute("SELECT COUNT(*) FROM world_sieges WHERE season_key=? "
                              "AND day=? AND hp=0",(season,day)).fetchone()[0]
            quests=con.execute("""SELECT COUNT(*) FROM quest_claims q
                JOIN players p ON p.season_key=q.season_key
                AND p.discord_user_id=q.discord_user_id
                WHERE q.season_key=? AND q.day=?
                AND p.review_state NOT IN ('flagged','disqualified')""",
                (season,day)).fetchone()[0]
            games=con.execute("""SELECT COUNT(*) FROM social_arcade_runs r
                JOIN players p ON p.season_key=r.season_key
                AND p.discord_user_id=r.discord_user_id
                WHERE r.season_key=? AND r.day=? AND r.status='finished'
                AND p.review_state NOT IN ('flagged','disqualified')""",
                (season,day)).fetchone()[0]
        lead=(_headline("lead",f"{_safe_name(top['mr_username'])} leads the snowball racket",
                        f"{int(top['points'])} verified individual points • {_safe_name(top['city'])}",
                        "Championship") if top else
              _headline("lead","Snowy streets, open scoreboard",
                        "No eligible scoring player has recorded a positive total yet.",
                        "Championship"))
        return (lead,
                _headline("streets","Snowball skirmishes across six cities",
                          f"{hits['attempts']} throws • {hits['hits']} hits • {hits['kos']} knockouts",
                          "Combat"),
                _headline("boss","The Snow Don's icy resistance",
                          f"{boss['damage']} verified damage by {boss['raiders']} raiders",
                          "Boss"),
                _headline("cities","Fortresses under siege",
                          f"{forts} of six city forts cleared", "Cities"),
                _headline("community","The community noticeboard",
                          f"{quests} quests claimed • {games} casual arcade runs",
                          "Community"))

    def newsroom(self, season: str, viewer: int, now: datetime) -> Newsroom:
        now=as_utc(now)
        state=self.store.season(season)
        with self.store.connect() as con:
            self._reader(con,season,viewer)
            rows=con.execute("""SELECT s.id,s.day,s.title,s.body,p.mr_username,p.city,
                COALESCE(d.verdict,'pending') status FROM wire_submissions s
                JOIN players p ON p.season_key=s.season_key AND p.discord_user_id=s.discord_user_id
                LEFT JOIN wire_decisions d ON d.submission_id=s.id
                WHERE s.season_key=? AND s.discord_user_id=?
                ORDER BY s.id DESC LIMIT 1""",(season,viewer)).fetchone()
            published=con.execute("""SELECT COUNT(*) FROM wire_submissions s
                JOIN wire_decisions d ON d.submission_id=s.id
                JOIN players p ON p.season_key=s.season_key
                AND p.discord_user_id=s.discord_user_id
                WHERE s.season_key=? AND d.verdict='approved'
                AND p.review_state NOT IN ('flagged','disqualified')""",(season,)).fetchone()[0]
            pending=con.execute("""SELECT COUNT(*) FROM wire_submissions s
                LEFT JOIN wire_decisions d ON d.submission_id=s.id
                WHERE s.season_key=? AND d.submission_id IS NULL""",(season,)).fetchone()[0]
        current=state.day(now)
        return Newsroom(state.phase(now),current,
                        CommunityEngine(self.store).latest_completed_day(season,now),
                        self.headlines(season,current) if current else (),
                        int(published),int(pending),self._story(rows) if rows else None)

    def edition(self, season: str, viewer: int, day: int, now: datetime) -> Edition:
        if not 1<=day<=7:
            raise WireError("Choose an edition from Day 1 through Day 7.")
        now=as_utc(now)
        state=self.store.season(season)
        if state.started_at is None or state.effective_now(now)<state.started_at+timedelta(days=day-1):
            raise WireError("That edition has not opened yet.")
        with self.store.connect() as con:
            self._reader(con,season,viewer)
            stories=self._stories(con,season,day=day)
        complete=CommunityEngine(self.store).latest_completed_day(season,now)>=day
        report=wire_story(CommunityEngine(self.store).recap(season,day,now),
                          practice=False) if complete else (
                          "LIVE DISPATCH — These figures may change until the day closes. "
                          "Official results will appear in the locked daily recap.")
        verified=self.headlines(season,day)
        return Edition(day,THEMES[day-1],complete,
                       "THE STREETS ARE TALKING" if not complete else
                       "THE DAY'S SNOWBALL LEDGER IS IN",verified,report,stories)


def story_caption(story: Story) -> str:
    """Explicitly label player fiction, not factual news; safe for Discord."""
    return (f"✉️ **COMMUNITY ROLEPLAY — DAY {story.day}**\n"
            f"**{story.title}**\n"
            f"*By {_safe_name(story.author)} of {_safe_name(story.city)}*\n"
            f"{story.body}\n"
            "*Player-submitted fiction; not a verified event result or prize.*")


def publication_text(edition: Edition, *, max_stories=2) -> str:
    """Bounded one-post completed-day news edition, without ping injection."""
    if not edition.complete:
        raise WireError("Only completed editions can be publicly broadcast.")
    out=[f"🗞️ **THE SNOWFALL WIRE 2.0 — DAY {edition.day}/7**",
         f"**{edition.theme}** · *Underworld Christmas Edition*",
         "*Factual game records below; player roleplay is labelled separately.*"]
    for h in edition.verified:
        out.append(f"**{h.category}: {h.title}** — {h.detail}")
    if edition.stories:
        out.append("✉️ **APPROVED COMMUNITY FICTION**")
        for story in edition.stories[:max_stories]:
            out.append(f"**{story.title}** — {_safe_name(story.author)} "
                       f"({_safe_name(story.city)}): {story.body[:220]}")
    out.append("*Honorary newspaper. Official individual prize standings are unchanged.*")
    return "\n".join(out)[:1880]
