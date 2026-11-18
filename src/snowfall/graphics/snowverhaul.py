"""Operation Snowfall v2.9.0a — complete, scoring-neutral graphical overhaul.

This module only renders image bytes and adds optional cosmetic portrait variants.
It never alters combat, winner selection, event points, RNG, or player balances.
Missing/corrupt image assets safely fall back to the original Pillow artwork.
"""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from pathlib import Path
import logging

from PIL import Image, ImageDraw, ImageEnhance, ImageOps

LOG = logging.getLogger(__name__)
ART = Path(__file__).resolve().parent / "art" / "v290"
_APPLIED = False
RESAMPLE = Image.Resampling.LANCZOS


@lru_cache(maxsize=32)
def _source(path: str) -> Image.Image | None:
    target = ART / path
    try:
        if not target.is_file() or target.stat().st_size > 12_000_000:
            return None
        with Image.open(target) as im:
            if im.width > 4096 or im.height > 4096:
                return None
            return im.convert("RGBA")
    except (ValueError, OSError):
        LOG.warning("Snowverhaul asset missing/broken: %s", path)
        return None


def _image(path, size=None, *, fit=False):
    src = _source(path)
    if src is None:
        return None
    if not size:
        return src.copy()
    if fit:
        return ImageOps.fit(src, size, method=RESAMPLE, centering=(0.5, 0.5))
    im = src.copy()
    im.thumbnail(size, RESAMPLE)
    return im


def _paste(canvas, path, box, *, fit=False, opacity=255):
    """Alpha composite asset with exact destination box; return whether asset exists."""
    x, y, r, b = box
    if r <= x or b <= y:
        return False
    im = _image(path, (r - x, b - y), fit=fit)
    if im is None:
        return False
    if opacity != 255:
        a = im.getchannel("A").point(lambda p: p * opacity // 255)
        im.putalpha(a)
    # when contain, anchor to central bottom to preserve full character figures
    xx = x + (r - x - im.width) // 2
    yy = y + (b - y - im.height) // 2
    canvas.alpha_composite(im, (xx, yy))
    return True


def _darken(canvas, box, alpha=105):
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rounded_rectangle(box, radius=14, fill=(8, 16, 29, alpha))
    canvas.alpha_composite(overlay)


def _finish(im):
    from snowfall.graphics.cards import _png

    return _png(im)


def _fallback(wrapper_name, original, *args, **kw):
    try:
        return wrapper_name(*args, **kw)
    except Exception:  # keep presentation faults out of event scoring
        LOG.exception("Snowverhaul renderer failed; using legacy card")
        return original(*args, **kw)


def _use_standard_snow_don_portraits(directory=None):
    """Use the new 0% scene only for the bot's default art installation.

    Custom supplied portrait directories (including tests and host overrides)
    keep the original 100%-10% portrait behaviour and cannot be obscured.
    """
    from snowfall.graphics import snow_don

    expected = Path(snow_don.__file__).resolve().parent / "art" / "boss"
    return directory is None and Path(snow_don.PORTRAITS).resolve() == expected.resolve()


def _snow_don_defeated(canvas, box):
    return _paste(canvas, "boss/snow_don_0.webp", box, fit=True)


def _showcase(showcase):
    """High-detail profile that preserves all resource values and wardrobe slots."""
    from snowfall.graphics.cards import WIDTH, HEIGHT, _bar, clean, _fit, font
    from snowfall.services.winter_fun import COSMETICS

    city = clean(showcase.player.city)
    im = _image("cosmetics/backgrounds/headquarters.webp", (WIDTH, HEIGHT), fit=True)
    if im is None:
        from snowfall.graphics.cards import _background

        im = _background(city).convert("RGBA")
    _darken(im, (27, 22, 931, 520), 135)
    # top banner is decorative, so name remains on its own contrast-safe panel
    eq = showcase.equipped
    banner = eq.get("banner")
    if banner:
        _paste(im, f"cosmetics/banners/{banner}.png", (20, 5, 940, 146), fit=True, opacity=172)
    dark = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(dark, "RGBA")
    d.rounded_rectangle((35, 36, 734, 169), radius=19, fill=(8, 18, 30, 203))
    d.rounded_rectangle((45, 194, 568, 510), radius=16, fill=(8, 22, 37, 210))
    d.rounded_rectangle((599, 185, 909, 457), radius=18, fill=(5, 18, 34, 220))
    im.alpha_composite(dark)
    # Portrait remains visible within a fixed image well; cosmetics sit above it.
    style = eq.get("portrait", "recruit")
    filename = style if style.endswith("_f") else style + "_m"
    if filename == "recruit_m":
        pass
    if _source(f"portraits/{filename}.webp") is None:
        filename = "recruit_m"
    # image fills a photo area; historical photo backdrop blends into dark office panel
    _paste(im, f"portraits/{filename}.webp", (607, 191, 902, 454), fit=True)
    trail = eq.get("trail")
    if trail:
        _paste(im, f"cosmetics/trails/{trail}.png", (607, 291, 905, 448), fit=False, opacity=180)
    gear = eq.get("gear")
    # Smaller mounted gear provides clear purchase feedback without hiding the face.
    if gear == "goggles":
        _paste(im, "cosmetics/gear/goggles.png", (680, 244, 829, 312), opacity=220)
    elif gear == "scarf":
        _paste(im, "cosmetics/gear/scarf.png", (664, 325, 855, 445), opacity=225)
    elif gear == "boots":
        _paste(im, "cosmetics/gear/boots.png", (791, 373, 896, 456))
    frame = eq.get("frame")
    if frame:
        _paste(im, f"cosmetics/frames/{frame}.png", (588, 175, 924, 472), fit=False)
    d = ImageDraw.Draw(im, "RGBA")
    d.text((55, 48), "OPERATION SNOWFALL · COLLECTOR CARD", font=font(17, True), fill="#d3ecfd")
    name = clean(showcase.player.mr_username, 42)
    d.text(
        (55, 79),
        _fit(d, name, 570, font(37, True)),
        font=font(37, True),
        fill="#ffffff",
        stroke_width=1,
        stroke_fill="#1a2533",
    )
    d.text(
        (57, 134),
        _fit(d, f"{city}  •  {clean(showcase.title, 38)}", 590, font(20)),
        font=font(20),
        fill="#fceacb",
    )
    rarity = showcase.best_rarity
    colour = {
        "Common": "#d2e6f0",
        "Rare": "#80d5ff",
        "Epic": "#d9b3ff",
        "Legendary": "#ffe1a1",
    }.get(rarity, "#d2e6f0")
    d.rounded_rectangle(
        (753, 100, 912, 147), radius=14, fill=(12, 26, 45, 233), outline=colour, width=3
    )
    d.text((763, 114), f"{rarity.upper()} STYLE", font=font(15, True), fill=colour)
    _bar(d, (59, 208, 542, 254), showcase.resources.warmth, 100, "Warmth", "#ef8b94")
    _bar(d, (59, 283, 542, 330), showcase.resources.snowballs, 12, "Snowballs", "#9bdbf5")
    _bar(d, (59, 358, 542, 406), showcase.resources.today_pvp, 300, "Daily PvP", "#a7e6b5")
    d.text(
        (62, 434),
        f"SEASON {showcase.points} PTS  ·  SNOWFLAKES {showcase.resources.snowflakes}",
        font=font(17, True),
        fill="#ffe1a2",
    )
    d.text(
        (62, 462),
        f"WARDROBE {showcase.owned_count}/{showcase.cosmetic_total}  ·  COSMETIC ONLY",
        font=font(14, True),
        fill="#d5eaf8",
    )
    d.text(
        (615, 445),
        _fit(
            d, f"GEAR: {COSMETICS[gear].name if gear in COSMETICS else 'None'}", 270, font(12, True)
        ),
        font=font(12, True),
        fill="#ffffff",
        stroke_width=2,
        stroke_fill="#172633",
    )
    badges = list(showcase.featured_badges)[:3]
    d.text(
        (615, 475),
        f"BADGES {showcase.badge_count}/{showcase.badge_total}",
        font=font(14, True),
        fill="#ffffff",
    )
    for idx, badge in enumerate(badges):
        x = 765 + idx * 49
        _paste(im, f"trophies/medals/{badge.key}.png", (x, 467, x + 44, 509))
    d = ImageDraw.Draw(im, "RGBA")
    d.text(
        (55, 516),
        f"ARCADE PASSPORT {len(getattr(showcase, 'arcade_stamps', ()))}/11 · NO BONUS POINTS OR PRIZES",
        font=font(11, True),
        fill="#d3e7f4",
    )
    return _finish(im)


def _battle(result, target, attacker="YOUR THROW", *, beat=None):

    base = _ORIG["cards.battle_card"](result, target, attacker, beat=beat)
    im = Image.open(BytesIO(base)).convert("RGBA")
    key = (
        "knockout"
        if result.knocked_out
        else "critical_hit"
        if result.critical
        else "snowball_impact"
        if result.hit
        else "miss"
    )
    # Every actual hit receives a secondary winter-shock bloom, purely decorative.
    # The critical / knockout visual is still the primary outcome indicator.
    if result.hit:
        _paste(im, "combat/frost_impact.png", (613, 235, 866, 445), opacity=105)
    _paste(im, f"combat/{key}.png", (628, 227, 912, 454), opacity=245)
    if result.hit and getattr(result, "armour_damage", 0) > 0:
        shield = "shield_shatter" if result.knocked_out else "shield_block"
        _paste(im, f"combat/{shield}.png", (775, 328, 918, 447), opacity=185)
    if beat is not None and getattr(beat, "streak", 0) >= 3:
        _paste(im, "combat/hit_streak.png", (572, 379, 736, 458), opacity=170)
    return _finish(im)


def _raid_board(report, *, viewer_id=None, city="Chicago"):
    """Cooperative snowy volley decoration; leaves official raid figures intact."""
    data = _ORIG["raid.raid_board_card"](report, viewer_id=viewer_id, city=city)
    im = Image.open(BytesIO(data)).convert("RGBA")
    if getattr(report, "enabled", True) and getattr(report, "contributors", 0) >= 2:
        # Bottom of artwork well, clear of shared HP, raider statistics and labels.
        _paste(im, "combat/snowball_volley.png", (650, 322, 908, 463), opacity=154)
    return _finish(im)


def _world_result(result):
    base = _ORIG["cards.world_result_card"](result)
    im = Image.open(BytesIO(base)).convert("RGBA")
    if result.kind == "siege":
        ratio = result.hp_after / max(1, result.max_hp)
        key = (
            "fort_breached" if ratio <= 0 else "fort_critical" if ratio <= 0.35 else "fort_damaged"
        )
        _paste(im, f"combat/{key}.png", (624, 204, 918, 452), opacity=240)
    elif result.kind == "boss" and result.hp_after <= 0 and _use_standard_snow_don_portraits():
        _snow_don_defeated(im, (640, 205, 919, 450))
    return _finish(im)


def _trophy_cabinet(cabinet):
    from snowfall.graphics.cards import _canvas, clean, font, _fit

    im = _image("trophies/backgrounds/trophy_cabinet.png", (960, 540), fit=True)
    if im is None:
        im, _ = _canvas(cabinet.city, "TROPHY CABINET", clean(cabinet.player_name))
    _darken(im, (27, 15, 931, 527), 172)
    d = ImageDraw.Draw(im, "RGBA")
    d.rounded_rectangle((29, 25, 930, 130), radius=16, fill=(11, 24, 39, 222))
    d.text((45, 34), "OPERATION SNOWFALL · TROPHY CABINET", font=font(24, True), fill="#fff0cf")
    d.text(
        (46, 82),
        _fit(
            d,
            clean(cabinet.player_name) + " • " + clean(cabinet.equipped_title),
            824,
            font(17, True),
        ),
        font=font(17, True),
        fill="#dbefff",
    )
    unlocked = sum(1 for x in cabinet.trophies if x.unlocked)
    d.text(
        (46, 142),
        f"COLLECTED {unlocked}/{len(cabinet.trophies)} · DECORATIVE TITLES ONLY",
        font=font(18, True),
        fill="#ffdb9b",
    )
    for i, t in enumerate(cabinet.trophies[:16]):
        col, row = i % 4, i // 4
        x = 41 + col * 227
        y = 185 + row * 77
        d.rounded_rectangle(
            (x, y, x + 216, y + 68),
            radius=11,
            fill=(12, 28, 42, 237),
            outline=(193, 152, 91, 189) if t.unlocked else (105, 123, 137, 125),
            width=2,
        )
        medal = _image(f"trophies/medals/{t.key}.png", (62, 62))
        if medal:
            if t.unlocked and t.rarity in ("Rare", "Legendary"):
                glow = "legendary_unlock" if t.rarity == "Legendary" else "rare_unlock"
                _paste(
                    im, f"trophies/effects/{glow}.png", (x + 1, y + 2, x + 64, y + 65), opacity=115
                )
            if not t.unlocked:
                medal = ImageEnhance.Brightness(medal).enhance(0.26)
            im.alpha_composite(
                medal, (x + 5 + (58 - medal.width) // 2, y + 4 + (58 - medal.height) // 2)
            )
        d.text(
            (x + 68, y + 11),
            _fit(d, t.badge, 139, font(13, True)),
            font=font(13, True),
            fill="#ffe3b5" if t.unlocked else "#9fadb8",
        )
        label = t.rarity if t.unlocked else f"{t.progress}/{t.target}"
        d.text((x + 68, y + 37), label, font=font(13), fill="#b4dbe9" if t.unlocked else "#97a8b3")
    d.text((55, 510), "NO BONUS POINTS, SNOWFLAKES OR PRIZES", font=font(13, True), fill="#d6eaf6")
    return _finish(im)


def _champions(players, cities, *, final=False):

    data = _ORIG["cards.champions_card"](players, cities, final=final)
    im = Image.open(BytesIO(data)).convert("RGBA")
    _paste(im, "trophies/awards/individual_champion.png", (721, 214, 908, 373), opacity=230)
    _paste(im, "trophies/awards/city_champion.png", (750, 382, 876, 486), opacity=220)
    return _finish(im)


def _territory_map(board, *, highlighted_city=None):
    from snowfall.graphics.cards import font, _fit

    im = _image("cities/map/six_city_territory_map.png", (960, 540), fit=True)
    if im is None:
        return _ORIG["territory.territory_map_card"](board, highlighted_city=highlighted_city)
    d = ImageDraw.Draw(im, "RGBA")
    # Landmark map is not real live gameplay; all live owner state is overlaid below.
    positions = {
        "Los Angeles": (240, 358),
        "Las Vegas": (289, 332),
        "Chicago": (648, 255),
        "Detroit": (703, 240),
        "Philadelphia": (808, 259),
        "New York": (820, 244),
    }
    home = {dist.contenders[0]: dist.owner for dist in board.districts if dist.kind == "home"}
    for city, (x, y) in positions.items():
        owned = home.get(city) == city
        col = board.banner(city).colour
        d.ellipse(
            (x - 12, y - 12, x + 12, y + 12),
            fill=(5, 19, 32, 170),
            outline=col if owned else "#aaaaaa",
            width=4,
        )
        if city == highlighted_city:
            d.ellipse((x - 17, y - 17, x + 17, y + 17), outline="#ffffff", width=2)
    d.rounded_rectangle(
        (24, 473, 934, 534), radius=11, fill=(8, 20, 34, 240), outline=(196, 207, 214, 150), width=2
    )
    label = f"DAY {board.day}/7" if board.day is not None else "AWAITING KICKOFF"
    d.text(
        (42, 480),
        label + "  ·  HONORARY DISTRICTS · NO EXTRA PRIZES",
        font=font(15, True),
        fill="#ffe4ae",
    )
    for idx, match in enumerate(board.matches[:3]):
        x = 42 + idx * 295
        own = match.rally_owner or "TIE"
        text = f"{match.city_a} vs {match.city_b}: {own}"
        d.text((x, 507), _fit(d, text, 282, font(12, True)), font=font(12, True), fill="#daeffa")
    return _finish(im)


def _banners(board):
    im = Image.open(BytesIO(_ORIG["territory.city_banners_card"](board))).convert("RGBA")
    for i, banner in enumerate(board.banners):
        col, row = i % 2, i // 2
        x = 51 + 451 * col
        y = 212 + 101 * row
        # Opaque plaque under each heraldic icon prevents underlying placeholder from showing.
        d = ImageDraw.Draw(im, "RGBA")
        d.rounded_rectangle((x + 7, y + 7, x + 67, y + 83), radius=9, fill=(9, 25, 40, 255))
        _paste(
            im,
            f"cities/crests/{banner.city.lower().replace(' ', '_')}_crest.png",
            (x + 4, y + 5, x + 71, y + 88),
        )
    return _finish(im)


def _city_territory(board, city):
    im = Image.open(BytesIO(_ORIG["territory.city_territory_card"](board, city))).convert("RGBA")
    d = ImageDraw.Draw(im, "RGBA")
    d.rounded_rectangle((695, 242, 836, 410), radius=10, fill=(9, 24, 37, 245))
    winners = any(
        getattr(m, "rally_owner", None) == city or getattr(m, "duel_owner", None) == city
        for m in board.matches
    )
    losses = any(
        city in (m.city_a, m.city_b) and (m.rally_owner or m.duel_owner) not in (None, city)
        for m in board.matches
    )
    if winners or losses:
        outcome = "city_victory_background" if winners else "city_defeat_background"
        _paste(im, f"cities/outcomes/{outcome}.png", (621, 219, 910, 444), fit=True, opacity=130)
    _paste(
        im,
        f"cities/banners/{city.lower().replace(' ', '_')}_district_banner.png",
        (692, 242, 836, 411),
    )
    return _finish(im)


def _case_file(snap, city="Chicago"):
    from snowfall.graphics.cards import _canvas, _fit, font

    if snap.case is None:
        return _ORIG["mystery.case_file_card"](snap, city)
    case = snap.case
    im, d = _canvas(city, f"CASE {case.day:02d} · CONFIDENTIAL", case.title.upper())
    _paste(im, f"mysteries/day_{case.day}.webp", (411, 211, 912, 466), fit=True, opacity=215)
    _paste(im, "mysteries/evidence_objects.webp", (791, 63, 901, 174), fit=True, opacity=210)
    d = ImageDraw.Draw(im, "RGBA")
    d.rounded_rectangle(
        (49, 211, 438, 467), radius=14, fill=(16, 25, 38, 237), outline="#c29f6e", width=3
    )
    for i, clue in enumerate(snap.clues):
        y = 230 + i * 68
        d.rounded_rectangle((63, y, 424, y + 61), radius=7, fill=(232, 221, 192, 240))
        d.text(
            (72, y + 5),
            f"EVIDENCE {i + 1:02d} · " + _fit(d, clue.label, 205, font(16, True)),
            font=font(16, True),
            fill="#3a302a",
        )
        d.text(
            (72, y + 33),
            "EXAMINED" if clue.found else "SEALED",
            font=font(14, True),
            fill="#226f4d" if clue.found else "#934a40",
        )
    found = sum(c.found for c in snap.clues)
    d.rounded_rectangle((52, 421, 913, 467), radius=8, fill=(9, 24, 38, 233))
    d.text(
        (65, 431),
        f"LEADS {found}/3  ·  ACCUSATIONS {snap.guesses}/2  ·  "
        + ("CASE CLOSED" if snap.solved else "INVESTIGATION OPEN"),
        font=font(16, True),
        fill="#ffe0ae",
    )
    d.rounded_rectangle((50, 479, 912, 517), radius=9, fill=(12, 28, 45, 246))
    line = (
        "SECRET DISCOVERED"
        if snap.secret is not None
        else "SECRET AVAILABLE"
        if snap.secret_ready
        else "SECRET HIDDEN · 2 CLUES + DAILY ACTIVITY"
    )
    d.text((64, 486), _fit(d, line, 829, font(18, True)), font=font(18, True), fill="#b3e8de")
    return _finish(im)


def _secret(snap, city="Chicago"):
    from snowfall.graphics.cards import _canvas, _fit, font

    im, d = _canvas(
        city, "SECRET CHRISTMAS ENCOUNTER", f"DAY {snap.day or '—'} · THE UNDERWORLD WHISPERS"
    )
    _paste(im, "mysteries/secret_encounter.webp", (51, 210, 909, 466), fit=True)
    d = ImageDraw.Draw(im, "RGBA")
    d.rounded_rectangle((60, 399, 904, 464), radius=12, fill=(17, 24, 33, 222))
    d.text(
        (71, 410),
        "CLASSIFIED · "
        + _fit(d, snap.secret.souvenir if snap.secret else "MYSTERY AWAITS", 730, font(19, True)),
        font=font(19, True),
        fill="#ffe1a5",
    )
    d.text(
        (62, 491),
        "HONORARY SOUVENIR ONLY · NO POINTS, SNOWFLAKES OR PRIZES",
        font=font(13, True),
        fill="#d8ecf7",
    )
    return _finish(im)


def _casebook(snap, city="Chicago"):
    """Illustrated seven-case ledger with verified saved progress, never spoilers."""
    from snowfall.graphics.cards import _canvas, _fit, font

    im, d = _canvas(city, "THE WINTER CASEBOOK", "SEVEN CASES · SEVEN HIDDEN MEMENTOS")
    _paste(im, "mysteries/case_board.webp", (575, 192, 919, 498), fit=True, opacity=118)
    _paste(im, "mysteries/classified_dossier.webp", (794, 36, 916, 169), fit=True, opacity=170)
    d = ImageDraw.Draw(im, "RGBA")
    for idx, entry in enumerate(snap.history[:7]):
        y = 199 + idx * 43
        d.rounded_rectangle(
            (43, y, 915, y + 39),
            radius=8,
            fill=(13, 30, 44, 222),
            outline=(154, 181, 190, 120),
            width=1,
        )
        day = getattr(entry, "day", idx + 1)
        if isinstance(day, int) and 1 <= day <= 7:
            _paste(im, f"mysteries/day_{day}.webp", (50, y + 3, 101, y + 36), fit=True, opacity=230)
        d.text(
            (111, y + 6),
            _fit(d, entry.title, 411, font(16, True)),
            font=font(16, True),
            fill="#fff0cd",
        )
        d.text((557, y + 7), f"{entry.clues}/3 clues", font=font(13, True), fill="#d5e7f4")
        d.text(
            (675, y + 7),
            "SOLVED" if entry.solved else "OPEN",
            font=font(13, True),
            fill="#98e7bd" if entry.solved else "#d6e0ec",
        )
        d.text(
            (785, y + 7),
            "MEMENTO" if entry.secret else "—",
            font=font(13, True),
            fill="#ffdb97" if entry.secret else "#9caeb7",
        )
    d.rounded_rectangle((49, 507, 913, 533), radius=8, fill=(13, 25, 38, 237))
    d.text(
        (61, 510),
        f"CASES CLOSED: {snap.solved_count}/7 · SECRET MEMENTOS: {snap.souvenirs_count}/7",
        font=font(13, True),
        fill="#ffdfa4",
    )
    return _finish(im)


def _arcade_lobby(lobby, city="Chicago"):
    """Five illustrated game tiles; the original personal-record values stay visible."""
    from snowfall.graphics.cards import _canvas, _fit, font

    im, d = _canvas(
        city, "THE WINTER ARCADE", f"DAY {lobby.day or '—'}/7 · FIVE GAMES · NO PAID PRIZES"
    )
    for idx, record in enumerate(lobby.records[:5]):
        col, row = idx % 2, idx // 2
        x, y = 43 + col * 454, 212 + row * 94
        d.rounded_rectangle(
            (x, y, x + 435, y + 85),
            radius=13,
            fill=(11, 29, 45, 240),
            outline=(184, 206, 219, 140),
            width=2,
        )
        mode = getattr(record, "mode", None)
        if mode not in ("gallery", "safe", "snowman", "catch", "trivia"):
            mode = ("gallery", "safe", "snowman", "catch", "trivia")[idx]
        _paste(im, f"arcade/{mode}.webp", (x + 6, y + 7, x + 120, y + 79), fit=True, opacity=226)
        d.text(
            (x + 133, y + 10),
            _fit(d, record.name, 282, font(17, True)),
            font=font(17, True),
            fill="#ffe3b4",
        )
        d.text(
            (x + 133, y + 45),
            f"BEST {record.personal_best}/100 · TODAY {record.attempts_today}/3",
            font=font(13, True),
            fill="#d4eafa",
        )
    d.text(
        (516, 493),
        f"TOUR {lobby.completed} RUNS · {len(lobby.stamps)} STAMPS",
        font=font(16, True),
        fill="#ffdfac",
    )
    return _finish(im)


def _arcade(session, city="Chicago"):
    im = Image.open(BytesIO(_ORIG["arcade.game_card"](session, city))).convert("RGBA")
    if session.current and session.mode in ("gallery", "safe", "snowman", "catch", "trivia"):
        _paste(im, f"arcade/{session.mode}.webp", (52, 211, 910, 463), fit=True)
        d = ImageDraw.Draw(im, "RGBA")
        d.rounded_rectangle((57, 215, 907, 294), radius=12, fill=(9, 20, 35, 213))
        d.rounded_rectangle((67, 227, 892, 243), radius=8, fill=(48, 66, 84, 244))
        total = max(1, getattr(session, "total_rounds", 1))
        step = max(0, min(total, getattr(session, "step", 0)))
        progress = int(825 * step / total)
        if progress:
            d.rounded_rectangle((67, 227, 67 + progress, 243), radius=7, fill="#a7ebd3")
        d.text(
            (77, 251),
            f"ROUND {step + 1}/{total}  ·  SCORE {session.score}/100",
            font=_font(21),
            fill="#ffe4ad",
        )
        d.rounded_rectangle((69, 424, 896, 458), radius=8, fill=(10, 22, 37, 165))
        d.text(
            (83, 432), "WINTER ARCADE  ·  " + session.title.upper(), font=_font(16), fill="#fceac5"
        )
    return _finish(im)


def _font(size):
    from snowfall.graphics.cards import font

    return font(size, True)


def _wire_front(edition=None, newsroom=None, city="Chicago"):
    """Illustrated broadsheet with its actual masthead and live verified reports."""
    from snowfall.graphics.cards import clean, _fit, font

    bg = (
        "final_day_edition"
        if edition is not None and getattr(edition, "day", None) == 7
        else "front_page_template"
    )
    im = _image(f"wire/backgrounds/{bg}.png", (960, 540), fit=True)
    if im is None:
        return _ORIG["wire.wire_front_card"](edition, newsroom, city)
    # This was the unused Pack H hero artwork in v2.9.0.
    _paste(im, "wire/banners/snowfall_wire_masthead.png", (33, 7, 927, 168), fit=False)
    d = ImageDraw.Draw(im, "RGBA")
    d.rounded_rectangle(
        (39, 164, 921, 251), radius=9, fill=(236, 222, 190, 244), outline="#745a41", width=2
    )
    day = edition.day if edition else newsroom.day if newsroom else None
    d.text(
        (54, 168),
        f"CHRISTMAS EDITION  ·  DAY {day or '—'}/7  ·  SIX CITIES",
        font=font(16, True),
        fill="#5b4034",
    )
    headline = edition.headline if edition else "THE STREETS ARE TALKING"
    d.text((55, 199), _fit(d, headline, 832, font(24, True)), font=font(24, True), fill="#382d25")
    articles = edition.verified if edition else newsroom.recent if newsroom else ()
    if any("city" in getattr(a, "category", "").lower() for a in articles):
        strip = "city_rivalry"
    elif edition and edition.day == 7:
        strip = "special_edition"
    else:
        strip = "breaking_news"
    _paste(im, f"wire/banners/{strip}.png", (734, 168, 905, 198), opacity=139)
    for idx in range(3):
        x = 51 + idx * 292
        d.rounded_rectangle(
            (x, 265, x + 279, 492),
            radius=8,
            fill=(240, 229, 204, 243),
            outline=(116, 90, 64, 236),
            width=2,
        )
        if idx >= len(articles):
            continue
        a = articles[idx]
        d.text(
            (x + 10, 274),
            _fit(d, a.category.upper(), 255, font(13, True)),
            font=font(13, True),
            fill="#8b4b37",
        )
        d.text(
            (x + 11, 306),
            _fit(d, a.title, 252, font(17, True)),
            font=font(17, True),
            fill="#2a3032",
        )
        words = clean(a.detail, 160).split()
        lines = [""]
        for word in words:
            trial = (lines[-1] + " " + word).strip()
            if d.textlength(trial, font=font(13)) > 251:
                lines.append(word)
            else:
                lines[-1] = trial
        for j, line in enumerate(lines[:6]):
            d.text((x + 11, 344 + j * 22), line, font=font(13), fill="#55483d")
    d.rectangle((48, 504, 907, 530), fill=(227, 210, 176, 246))
    d.text(
        (56, 508),
        "VERIFIED RESULTS ARE DISTINCT FROM PLAYER FICTION · NO EXTRA PRIZES",
        font=font(12, True),
        fill="#584737",
    )
    return _finish(im)


def _wire_stories(stories, city="Chicago"):
    from snowfall.graphics.cards import _fit, font, clean

    im = _image("wire/backgrounds/newsroom_editorial.png", (960, 540), fit=True)
    if im is None:
        return _ORIG["wire.wire_stories_card"](stories, city)
    _darken(im, (26, 13, 932, 527), 158)
    d = ImageDraw.Draw(im, "RGBA")
    d.rounded_rectangle((35, 24, 928, 172), radius=12, fill=(11, 22, 36, 226))
    _paste(im, "wire/overlays/classified_notice.png", (714, 37, 907, 163), opacity=145)
    d.text((53, 40), "LETTERS TO THE EDITOR", font=font(33, True), fill="#ffdfab")
    d.text(
        (55, 107),
        "APPROVED PLAYER FICTION · NOT VERIFIED COMPETITION RESULTS",
        font=font(14, True),
        fill="#e5f4fc",
    )
    for idx, story in enumerate(stories[:4]):
        y = 190 + idx * 73
        d.rounded_rectangle(
            (42, y, 705, y + 66),
            radius=9,
            fill=(14, 29, 45, 236),
            outline=(185, 151, 112, 161),
            width=2,
        )
        d.text(
            (59, y + 8),
            _fit(d, f"DAY {story.day}: {story.title}", 624, font(19, True)),
            font=font(19, True),
            fill="#ffe8b7",
        )
        d.text(
            (59, y + 39),
            _fit(d, f"By {story.author} · {story.city}", 620, font(14)),
            font=font(14),
            fill="#d2e9f6",
        )
    # Generic illustrated contributor plaque, not an invented user photograph.
    d.rounded_rectangle((729, 188, 920, 499), radius=12, fill=(10, 23, 35, 244))
    _paste(im, "wire/overlays/featured_player_frame.png", (724, 185, 923, 498), fit=False)
    d = ImageDraw.Draw(im, "RGBA")
    featured = stories[0] if stories else None
    d.rounded_rectangle((748, 293, 899, 395), radius=9, fill=(10, 22, 37, 221))
    if featured:
        d.text((757, 301), "FEATURED WRITER", font=font(13, True), fill="#ffe1ab")
        d.text(
            (756, 329),
            _fit(d, clean(featured.author, 34), 130, font(15, True)),
            font=font(15, True),
            fill="#ffffff",
        )
        d.text(
            (757, 361),
            _fit(d, clean(featured.city, 26), 134, font(12)),
            font=font(12),
            fill="#d5eaf7",
        )
    else:
        d.text((757, 311), "AWAITING A", font=font(14, True), fill="#f2e0bc")
        d.text((757, 343), "STORY", font=font(18, True), fill="#d7eaf6")
    return _finish(im)


def _wire_report(report):
    im = Image.open(BytesIO(_ORIG["community.wire_report_card"](report))).convert("RGBA")
    _paste(im, "wire/banners/city_dispatch.png", (651, 57, 898, 155), opacity=190)
    return _finish(im)


def _gif_from_scenes(paths, label, maximum_bytes):
    """Short cinematic storyboard, deliberately lower than Discord attachment cap."""
    frames = []
    for i, path in enumerate(paths):
        im = _image(f"boss/{path}.webp", (480, 270), fit=True)
        if im is None:
            return None
        d = ImageDraw.Draw(im, "RGBA")
        d.rounded_rectangle(
            (17, 210, 463, 263), radius=11, fill=(10, 21, 35, 224), outline="#ffd99d", width=2
        )
        d.text((30, 219), label, font=_font(20), fill="#ffdfa7")
        d.text(
            (32, 245),
            "ALL RAIDERS SHARE THE VICTORY" if "FALLEN" in label else "SNOW DON BOSS ENCOUNTER",
            font=_font(11),
            fill="#e5f5ff",
        )
        # real unique frame visual so GIF optimization does not collapse frames
        d.ellipse((20 + i * 32, 188, 28 + i * 32, 196), fill="#fff5d1")
        frames.append(im.convert("RGB").quantize(colors=72, method=Image.Quantize.MEDIANCUT))
    out = BytesIO()
    frames[0].save(
        out,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=[175] * (len(frames) - 1) + [1000],
        loop=0,
        optimize=True,
        disposal=2,
    )
    return out.getvalue() if out.tell() < maximum_bytes else None


def _phase_anim(result, *, maximum_bytes=4_000_000):
    from snowfall.services.boss_personality import phase_transitions

    phases = phase_transitions(result)
    if not phases:
        return None
    frames = [
        "rage_tommy",
        "rage_snowball",
        "phase_ice",
        "phase_frostfire",
        "rage_tommy",
        "phase_ice",
        "rage_snowball",
        "phase_frostfire",
        "phase_ice",
    ]
    data = _gif_from_scenes(frames, f"BOSS PHASE {phases[-1]}% REACHED", maximum_bytes)
    return (
        data
        if data is not None
        else _ORIG["raid.phase_transition_animation"](result, maximum_bytes=maximum_bytes)
    )


def _final_anim(result, *, maximum_bytes=4_000_000):
    if result.kind != "boss" or not result.final_blow or result.echo or result.repeated:
        return None
    frames = [
        "rage_tommy",
        "rage_snowball",
        "phase_ice",
        "phase_frostfire",
        "rage_tommy",
        "phase_frostfire",
        "phase_ice",
        "final_defeat",
        "snow_don_0",
        "final_defeat",
        "snow_don_0",
        "raid_celebration",
        "victory_screen",
        "raid_celebration",
        "victory_screen",
        "final_defeat",
    ]
    data = _gif_from_scenes(frames, "THE SNOW DON HAS FALLEN!", maximum_bytes)
    return (
        data
        if data is not None
        else _ORIG["raid.final_defeat_cinematic"](result, maximum_bytes=maximum_bytes)
    )


def shop_card(snapshot=None) -> bytes:
    from snowfall.graphics.cards import font

    im = _image("cosmetics/backgrounds/shop.webp", (960, 540), fit=True)
    if im is None:
        raise FileNotFoundError("Shop artwork missing")
    d = ImageDraw.Draw(im, "RGBA")
    d.rounded_rectangle((38, 28, 918, 168), radius=19, fill=(10, 26, 41, 215))
    d.text((53, 45), "OPERATION SNOWFALL · COSMETIC SHOP", font=font(30, True), fill="#ffe3aa")
    d.text(
        (55, 112),
        f"YOUR SNOWFLAKES: {snapshot.balance}" if snapshot else "WINTER EQUIPMENT & WARDROBE",
        font=font(21, True),
        fill="#eaf9ff",
    )
    return _finish(im)


_ORIG = {}


def _install(module, key, name, replacement):
    existing = getattr(module, name)
    _ORIG[key] = existing

    def wrapped(*args, **kwargs):
        return _fallback(replacement, existing, *args, **kwargs)

    wrapped.__name__ = existing.__name__
    wrapped.__doc__ = existing.__doc__
    setattr(module, name, wrapped)


def activate():
    global _APPLIED
    if _APPLIED:
        return
    from snowfall.graphics import (
        cards,
        showcase_cards,
        territory_cards,
        mystery_cards,
        social_arcade_cards,
        raid_cards,
        wire_cards,
        community_cards,
        snow_don,
    )
    from snowfall.services import winter_fun

    # Cosmetics remain entirely cosmetic; original items, prices and prizes unchanged.
    female = (
        ("recruit_f", "Recruit — Female", 0, "Common"),
        ("noir_detective_f", "Noir Detective — Female", 8, "Common"),
        ("winter_enforcer_f", "Winter Enforcer — Female", 14, "Epic"),
        ("frost_spectre_f", "Frost Spectre — Female", 18, "Legendary"),
    )
    for key, name, cost, rarity in female:
        if key not in winter_fun.COSMETICS:
            winter_fun.COSMETICS[key] = winter_fun.Cosmetic(
                key,
                name,
                "portrait",
                cost,
                "Alternative illustrated character portrait",
                rarity=rarity,
            )
    _install(showcase_cards, "showcase.profile_showcase_card", "profile_showcase_card", _showcase)
    _install(cards, "cards.battle_card", "battle_card", _battle)
    _install(cards, "cards.world_result_card", "world_result_card", _world_result)
    _install(raid_cards, "raid.raid_board_card", "raid_board_card", _raid_board)
    _install(cards, "cards.trophy_cabinet_card", "trophy_cabinet_card", _trophy_cabinet)
    _install(cards, "cards.champions_card", "champions_card", _champions)
    _install(territory_cards, "territory.territory_map_card", "territory_map_card", _territory_map)
    _install(territory_cards, "territory.city_banners_card", "city_banners_card", _banners)
    _install(
        territory_cards, "territory.city_territory_card", "city_territory_card", _city_territory
    )
    _install(mystery_cards, "mystery.case_file_card", "case_file_card", _case_file)
    _install(mystery_cards, "mystery.casebook_card", "casebook_card", _casebook)
    _install(mystery_cards, "mystery.secret_postcard_card", "secret_postcard_card", _secret)
    _install(social_arcade_cards, "arcade.game_card", "game_card", _arcade)
    _install(social_arcade_cards, "arcade.lobby_card", "lobby_card", _arcade_lobby)
    _install(wire_cards, "wire.wire_front_card", "wire_front_card", _wire_front)
    _install(wire_cards, "wire.wire_stories_card", "wire_stories_card", _wire_stories)
    _install(community_cards, "community.wire_report_card", "wire_report_card", _wire_report)
    _install(
        raid_cards, "raid.phase_transition_animation", "phase_transition_animation", _phase_anim
    )
    _install(raid_cards, "raid.final_defeat_cinematic", "final_defeat_cinematic", _final_anim)
    # Modules which import functions by value keep aliases. Update aliases intentionally.
    raid_cards.world_result_card = cards.world_result_card
    raid_cards.draw_portrait = snow_don.draw_portrait
    # Live Snow Don at 0%: a dedicated illustrated defeated scene, not the 10% portrait.
    original_draw = snow_don.draw_portrait

    def zero_portrait(canvas, remaining_hp, max_hp, box, *, directory=None):
        if (
            remaining_hp <= 0
            and _use_standard_snow_don_portraits(directory)
            and _snow_don_defeated(canvas, box)
        ):
            return 0
        return original_draw(canvas, remaining_hp, max_hp, box, directory=directory)

    snow_don.draw_portrait = zero_portrait
    cards.draw_portrait = zero_portrait
    raid_cards.draw_portrait = zero_portrait
    _APPLIED = True
