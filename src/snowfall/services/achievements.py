"""Cosmetic, season-scoped trophies and personal records from immutable event history.

Trophies grant no gameplay resources, ledger points, paid rewards, or city bonuses.
The only writable state is the player's currently equipped display title.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import NamedTuple

from snowfall.db.store import Store


class TrophyError(ValueError):
    pass


@dataclass(frozen=True)
class CombatRecords:
    pvp_throws: int
    pvp_hits: int
    critical_hits: int
    knockouts: int
    unique_rivals: int
    best_hit: int
    boss_damage: int
    boss_attacks: int
    siege_damage: int
    siege_attacks: int
    quests: int
    gifts: int
    golden_gifts: int
    active_days: int
    hot_chocolates: int
    successful_boss_hits: int
    cosmetics_unlocked: int = 0
    style_slots: int = 0

    @property
    def accuracy(self) -> float:
        return round(100 * self.pvp_hits / self.pvp_throws, 1) if self.pvp_throws else 0.0


class TrophySpec(NamedTuple):
    key: str
    badge: str
    title: str
    description: str
    measure: str
    required: int


TROPHIES = (
    TrophySpec('first_flurry', 'First Flurry', 'Snowball Rookie', 'Land your first PvP hit', 'pvp_hits', 1),
    TrophySpec('deadeye', 'Deadeye', 'Frostbite Marksman', 'Land 25 PvP hits', 'pvp_hits', 25),
    TrophySpec('rival_hunter', 'Rival Hunter', 'Snowball Enforcer', 'Hit 8 different rivals', 'unique_rivals', 8),
    TrophySpec('critical_ace', 'Critical Ace', 'Ice-Cold Sharpshooter', 'Land 5 critical hits', 'critical_hits', 5),
    TrophySpec('knockout_artist', 'Knockout Artist', 'Winter Hitman', 'Knock out 3 rivals', 'knockouts', 3),
    TrophySpec('don_destroyer', 'Don Destroyer', 'Don Destroyer', 'Deal 250 shared Snow Don damage', 'boss_damage', 250),
    TrophySpec('boss_regular', 'Don’s Nemesis', 'Snow Don Nemesis', 'Land 15 boss hits', 'successful_boss_hits', 15),
    TrophySpec('fort_breaker', 'Fort Breaker', 'Siege Specialist', 'Deal 150 shared fortress damage', 'siege_damage', 150),
    TrophySpec('quest_master', 'Mission Master', 'Winter Operative', 'Claim 10 quests', 'quests', 10),
    TrophySpec('gift_collector', 'Gift Hunter', 'Present Pilferer', 'Open 5 mystery presents', 'gifts', 5),
    TrophySpec('golden_legend', 'Golden Legend', 'Golden Snowballer', 'Win a Golden Snowball', 'golden_gifts', 1),
    TrophySpec('seven_days', 'Seven-Day Veteran', 'Snowfall Veteran', 'Score on all seven event days', 'active_days', 7),
    TrophySpec('cocoa_club', 'Hot Chocolate Club', 'Cocoa Connoisseur', 'Use 5 Hot Chocolates', 'hot_chocolates', 5),
    TrophySpec('first_style', 'Fresh Threads', 'Winter Trendsetter', 'Unlock your first cosmetic', 'cosmetics_unlocked', 1),
    TrophySpec('collector', 'Collector’s Club', 'Snowfall Collector', 'Collect five cosmetics', 'cosmetics_unlocked', 5),
    TrophySpec('full_outfit', 'Dressed to Impress', 'Frost Fashion Icon',
               'Equip a frame, trail, gear, banner and portrait', 'style_slots', 5),
)
SPEC_BY_KEY = {spec.key: spec for spec in TROPHIES}
DEFAULT_TITLE = 'Snowball Recruit'
BADGE_RARITIES = {
    'first_flurry': 'Common', 'deadeye': 'Rare', 'rival_hunter': 'Rare',
    'critical_ace': 'Epic', 'knockout_artist': 'Epic', 'don_destroyer': 'Epic',
    'boss_regular': 'Rare', 'fort_breaker': 'Rare', 'quest_master': 'Rare',
    'gift_collector': 'Common', 'golden_legend': 'Legendary',
    'seven_days': 'Legendary', 'cocoa_club': 'Common',
    'first_style': 'Common', 'collector': 'Rare', 'full_outfit': 'Legendary',
}


@dataclass(frozen=True)
class Trophy:
    key: str
    badge: str
    title: str
    description: str
    progress: int
    target: int
    unlocked: bool

    @property
    def rarity(self) -> str:
        return BADGE_RARITIES.get(self.key, 'Common')


@dataclass(frozen=True)
class Cabinet:
    player_name: str
    city: str
    equipped_title: str
    trophies: tuple[Trophy, ...]
    records: CombatRecords

    @property
    def unlocked_count(self) -> int:
        return sum(t.unlocked for t in self.trophies)

    @property
    def equipped_key(self) -> str:
        return next((t.key for t in self.trophies if t.unlocked and
                     t.title == self.equipped_title), 'none')


def _number(row, key: str) -> int:
    return int(row[key] or 0)


def _records(con, key: str, player_id: int) -> CombatRecords:
    c = con.execute('''SELECT COUNT(*) AS throws,
        SUM(CASE WHEN hit=1 THEN 1 ELSE 0 END) AS hits,
        SUM(CASE WHEN hit=1 AND critical=1 THEN 1 ELSE 0 END) AS crits,
        SUM(CASE WHEN hit=1 AND knocked_out=1 THEN 1 ELSE 0 END) AS kos,
        COUNT(DISTINCT CASE WHEN hit=1 THEN target_id END) AS rivals,
        MAX(CASE WHEN hit=1 THEN armour_damage + warmth_damage ELSE 0 END) AS best
        FROM combat_events WHERE season_key=? AND attacker_id=?''', (key, player_id)).fetchone()
    w = con.execute('''SELECT
        SUM(CASE WHEN kind='boss' AND echo=0 THEN damage ELSE 0 END) AS boss_damage,
        SUM(CASE WHEN kind='boss' THEN 1 ELSE 0 END) AS boss_attacks,
        SUM(CASE WHEN kind='boss' AND hit=1 THEN 1 ELSE 0 END) AS boss_hits,
        SUM(CASE WHEN kind='siege' AND echo=0 THEN damage ELSE 0 END) AS siege_damage,
        SUM(CASE WHEN kind='siege' THEN 1 ELSE 0 END) AS siege_attacks
        FROM pve_events WHERE season_key=? AND attacker_id=?''', (key, player_id)).fetchone()
    q = con.execute('SELECT COUNT(*) FROM quest_claims WHERE season_key=? AND discord_user_id=?',
                    (key, player_id)).fetchone()[0]
    g = con.execute('''SELECT COUNT(*) AS gifts,
        SUM(CASE WHEN reward='golden' OR actual_reward='golden' THEN 1 ELSE 0 END) AS golden
        FROM mystery_gifts WHERE season_key=? AND discord_user_id=?''', (key, player_id)).fetchone()
    active = con.execute('''SELECT COUNT(DISTINCT day) FROM score_ledger
        WHERE season_key=? AND player_id=? AND points>0''', (key, player_id)).fetchone()[0]
    cocoa = con.execute('''SELECT COUNT(*) FROM item_events
        WHERE season_key=? AND discord_user_id=? AND operation='use' AND item_key='cocoa' ''',
        (key, player_id)).fetchone()[0]
    cosmetics = con.execute('''SELECT COUNT(*) FROM cosmetic_unlocks
        WHERE season_key=? AND discord_user_id=?''', (key, player_id)).fetchone()[0]
    # Count only still-owned equipment keys in the canonical five display slots.
    from snowfall.services.winter_fun import COSMETICS, SLOTS
    valid = con.execute('''SELECT e.category,e.cosmetic_key FROM cosmetic_equipped e
        INNER JOIN cosmetic_unlocks u ON u.season_key=e.season_key
          AND u.discord_user_id=e.discord_user_id AND u.cosmetic_key=e.cosmetic_key
        WHERE e.season_key=? AND e.discord_user_id=?''', (key, player_id)).fetchall()
    slots = sum(1 for category, cosmetic in valid
                if category in SLOTS and cosmetic in COSMETICS and
                COSMETICS[cosmetic].category == category)
    return CombatRecords(_number(c, 'throws'), _number(c, 'hits'), _number(c, 'crits'),
                         _number(c, 'kos'), _number(c, 'rivals'), _number(c, 'best'),
                         _number(w, 'boss_damage'), _number(w, 'boss_attacks'),
                         _number(w, 'siege_damage'), _number(w, 'siege_attacks'),
                         int(q), _number(g, 'gifts'), _number(g, 'golden'), int(active),
                         int(cocoa), _number(w, 'boss_hits'), int(cosmetics), slots)


class AchievementEngine:
    def __init__(self, store: Store):
        self.store = store

    def cabinet(self, season: str, user_id: int) -> Cabinet:
        with self.store.connect() as con:
            player = con.execute('''SELECT mr_username, city FROM players
                WHERE season_key=? AND discord_user_id=?''', (season, user_id)).fetchone()
            if player is None:
                raise TrophyError('Register with `/snow join` to begin earning trophies.')
            stats = _records(con, season, user_id)
            trophies = tuple(Trophy(t.key, t.badge, t.title, t.description,
                                    getattr(stats, t.measure), t.required,
                                    getattr(stats, t.measure) >= t.required) for t in TROPHIES)
            equipped = con.execute('''SELECT title_key FROM player_titles
                WHERE season_key=? AND discord_user_id=?''', (season, user_id)).fetchone()
            equipped_key = equipped['title_key'] if equipped else 'none'
            chosen = next((t.title for t in trophies if t.key == equipped_key and t.unlocked),
                          DEFAULT_TITLE)
            return Cabinet(player['mr_username'], player['city'], chosen, trophies, stats)

    def equip(self, season: str, user_id: int, title_key: str) -> str:
        if title_key not in SPEC_BY_KEY and title_key != 'none':
            raise TrophyError('Unknown title. Select a title from your Trophy Cabinet.')
        with self.store.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            player = con.execute('SELECT 1 FROM players WHERE season_key=? AND discord_user_id=?',
                                 (season, user_id)).fetchone()
            if player is None:
                raise TrophyError('Register before equipping a title.')
            if title_key != 'none':
                t = SPEC_BY_KEY[title_key]
                records = _records(con, season, user_id)
                if getattr(records, t.measure) < t.required:
                    raise TrophyError('That cosmetic title is still locked.')
            con.execute('''INSERT INTO player_titles
                (season_key,discord_user_id,title_key,updated_at_utc)
                VALUES (?,?,?,?) ON CONFLICT(season_key,discord_user_id)
                DO UPDATE SET title_key=excluded.title_key,updated_at_utc=excluded.updated_at_utc''',
                (season, user_id, title_key, datetime.now(timezone.utc).isoformat()))
            return DEFAULT_TITLE if title_key == 'none' else SPEC_BY_KEY[title_key].title
