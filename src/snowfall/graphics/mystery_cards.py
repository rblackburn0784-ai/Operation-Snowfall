"""Illustrated detective case files; locally generated, spoiler-safe, pure graphics."""
from __future__ import annotations

from snowfall.graphics.cards import _canvas, _fit, _png, font

INK = "#f7ebd4"
GOLD = "#ffda8f"


def _evidence_note(draw, x, y, number, clue):
    # 1930s paper evidence pinned to the wall; no culprit text or answers.
    draw.rounded_rectangle((x, y, x+255, y+150), radius=9,
                           fill=(238, 226, 193, 247), outline=(109, 83, 50, 255), width=3)
    draw.ellipse((x+117, y+7, x+130, y+20), fill=(151, 41, 45, 255))
    draw.text((x+15, y+32), f"EVIDENCE NO. {number:02d}", font=font(15, True),
              fill="#60392f")
    draw.text((x+15, y+64), _fit(draw, clue.label.upper(), 221, font(16, True)),
              font=font(16, True), fill="#2a3542")
    status = "EXAMINED" if clue.found else "SEALED"
    colour = "#347852" if clue.found else "#92433c"
    draw.rectangle((x+14, y+109, x+241, y+135), fill=colour)
    draw.text((x+52, y+111), status, font=font(16, True), fill="#ffffff")


def case_file_card(snap, city="Chicago") -> bytes:
    if snap.case is None:
        return casebook_card(snap, city)
    case = snap.case
    im, d = _canvas(city, f"CASE {case.day:02d} • CONFIDENTIAL",
                    case.title.upper())
    d.rounded_rectangle((46, 204, 915, 454), radius=17,
                        fill=(36, 27, 28, 238), outline=(235, 197, 126, 190), width=3)
    for i, clue in enumerate(snap.clues):
        _evidence_note(d, 63 + 278*i, 231, i+1, clue)
    found = sum(c.found for c in snap.clues)
    d.text((73, 404), f"LEADS {found}/3  •  ACCUSATIONS {snap.guesses}/2  •  "
           + ("CASE CLOSED" if snap.solved else "INVESTIGATION OPEN"),
           font=font(19, True), fill=GOLD)
    d.rounded_rectangle((50, 471, 911, 514), radius=12,
                        fill=(11, 25, 42, 240))
    line = ("SECRET DISCOVERED" if snap.secret is not None else
            "SECRET AVAILABLE" if snap.secret_ready else
            "SECRET HIDDEN • 2 CLUES + DAILY ACTIVITY")
    d.text((66, 481), _fit(d, line, 808, font(19, True)),
           font=font(19, True), fill="#bdebe5")
    return _png(im)


def casebook_card(snap, city="Chicago") -> bytes:
    im, d = _canvas(city, "THE WINTER CASEBOOK",
                    "SEVEN DAYS  •  SEVEN CASES  •  SEVEN HIDDEN MEMENTOS")
    for i, entry in enumerate(snap.history):
        y = 218 + i*39
        d.rounded_rectangle((55, y, 902, y+34), radius=9,
                            fill=(16, 32, 49, 235),
                            outline=(164, 198, 213, 95))
        tint = "#b8edcb" if entry.solved else "#c7d9e5"
        d.text((70, y+6), f"{entry.day:02d}", font=font(18, True), fill=GOLD)
        d.text((117, y+7), _fit(d, entry.title, 410, font(17, True)),
               font=font(17, True), fill=INK)
        d.text((552, y+8), f"{entry.clues}/3 clues", font=font(13, True),
               fill="#d2e5ef")
        d.text((666, y+7), "SOLVED" if entry.solved else "OPEN",
               font=font(15, True), fill=tint)
        d.text((775, y+7), "MEMENTO" if entry.secret else "—",
               font=font(13, True), fill="#ffdf9b" if entry.secret else "#879da9")
    d.text((59, 500), f"CASES CLOSED: {snap.solved_count}/7  •  "
           f"SECRET MEMENTOS: {snap.souvenirs_count}/7",
           font=font(16, True), fill=GOLD)
    return _png(im)


def secret_postcard_card(snap, city="Chicago") -> bytes:
    im, d = _canvas(city, "SECRET CHRISTMAS ENCOUNTER",
                    f"DAY {snap.day or '—'}  •  THE UNDERWORLD WHISPERS")
    d.rounded_rectangle((60, 217, 892, 468), radius=21,
                        fill=(20, 36, 55, 242), outline=(241, 207, 145, 232), width=4)
    # Geometric winter star, sealed envelope and twinkling snowfall.
    d.polygon([(479, 241), (501, 292), (558, 300), (514, 338),
               (529, 397), (479, 363), (429, 397), (445, 338),
               (400, 300), (458, 292)], fill="#f6dfa1")
    d.rounded_rectangle((390, 339, 568, 411), radius=8,
                        fill="#e7e6da", outline="#e3b972", width=3)
    d.line((390, 340, 479, 385, 568, 340), fill="#987f67", width=3)
    d.text((89, 257), "CLASSIFIED", font=font(24, True), fill=GOLD)
    d.text((87, 429), _fit(d, snap.secret.souvenir if snap.secret else
                          "MYSTERY AWAITS", 700, font(20, True)),
           font=font(20, True), fill="#deecf5")
    d.text((62, 494), "HONORARY SOUVENIR ONLY • NO POINTS, SNOWFLAKES OR PRIZES",
           font=font(14, True), fill="#c4ddea")
    return _png(im)
