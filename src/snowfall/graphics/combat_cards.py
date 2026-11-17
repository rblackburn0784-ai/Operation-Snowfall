"""Original, offline 1930s winter PvP graphics; presentation only."""
from __future__ import annotations

from PIL import ImageDraw

from snowfall.graphics.cards import _canvas, _fit, _png, clean, font


def decorate_battle(image, result, beat) -> None:
    """Paint a v0.2.3 television-style commentary overlay on an existing card."""
    d = ImageDraw.Draw(image, "RGBA")
    # Coordinates intentionally sit in the right-hand action area of the card.
    d.rounded_rectangle((566, 207, 922, 247), radius=11,
                        fill=(13, 31, 52, 238), outline=(177, 221, 239, 194), width=2)
    colour = "#f9d58e" if result.critical or result.knocked_out else "#d0ecfd"
    d.text((583, 216), _fit(d, beat.headline, 316, font(20, True)),
           font=font(20, True), fill=colour)
    # Snowblast is static and seeded by the stored combat result, not by RNG.
    if result.hit:
        cx, cy = 832, 340
        for i in range(12):
            from math import sin, cos, pi
            angle = 2 * pi * i / 12
            inner, outer = 43, 69 + 4 * (i % 3)
            d.line((cx + int(inner * cos(angle)), cy + int(inner * sin(angle)),
                    cx + int(outer * cos(angle)), cy + int(outer * sin(angle))),
                   fill=(248, 229, 174, 192) if result.critical else (180, 233, 254, 170),
                   width=3)
    if beat.revenge:
        d.rounded_rectangle((578, 369, 910, 404), radius=10,
                            fill=(112, 57, 42, 245), outline=(255, 214, 126, 245), width=2)
        d.text((612, 376), "REVENGE LANDED!", font=font(20, True), fill="#ffe8ab")
    d.rounded_rectangle((575, 413, 921, 461), radius=12,
                        fill=(13, 31, 51, 244), outline=(158, 213, 236, 190), width=2)
    d.text((591, 419), f"HIT STREAK   {beat.streak}  (BEST {beat.personal_best})",
           font=font(17, True), fill="#e2f7fd")
    d.text((591, 440), f"RIVALRY HITS   {beat.pair_hits} : {beat.pair_received}",
           font=font(14, True), fill="#a9d9ed")


def rivalry_card(intel, city: str = "Chicago") -> bytes:
    image, d = _canvas(city, "RIVALRY DOSSIER",
                       f"Scored-hit streak {intel.current_streak}  •  Best {intel.best_streak}  •  "
                       f"{len(intel.revenge_alerts)} revenge alert(s)")
    d.rounded_rectangle((49, 215, 910, 285), radius=15, fill=(10, 27, 46, 220),
                        outline=(167, 210, 240, 130), width=2)
    d.text((65, 226), f"YOUR PVP HITS: {intel.total_hits}/{intel.total_attacks} THROWS",
           font=font(21, True), fill="#e1f3ff")
    d.text((65, 255), f"RETALIATIONS LANDED: {intel.revenge_count}",
           font=font(17, True), fill="#ffe1b5")
    leaders = intel.rivalries[:3]
    for i in range(3):
        x = 53 + 290 * i
        d.rounded_rectangle((x, 315, x + 273, 469), radius=15,
                            fill=(12, 31, 51, 233), outline=(149, 210, 239, 140), width=2)
        if i >= len(leaders):
            d.text((x + 19, 367), "NO RIVAL YET", font=font(18, True), fill="#95b4c6")
            continue
        r = leaders[i]
        d.text((x + 16, 330), _fit(d, clean(r.name), 237, font(21, True)),
               font=font(21, True), fill="#f7f9ff")
        d.text((x + 16, 361), clean(r.city), font=font(15), fill="#b3d9e8")
        d.text((x + 16, 395), f"HITS {r.hits}-{r.received_hits}",
               font=font(21, True), fill="#fae0a3")
        d.text((x + 16, 431), "REVENGE AVAILABLE" if r.pending_revenge
               else f"{r.revenges} RETALIATION(S)",
               font=font(15, True), fill="#ffe1a2" if r.pending_revenge else "#b0ddec")
    d.text((57, 491), "PRIVATE INTELLIGENCE  •  NO EXTRA POINTS OR PRIZES",
           font=font(15, True), fill="#d3e9f6")
    return _png(image)
