"""Original Pillow schematic city-war map, city banners and honourary district art.

All data comes from TerritoryBoard; rendering is pure and safe to skip if
images are unavailable. Fictional districts are not geographical assertions.
"""
from __future__ import annotations

from PIL import Image, ImageDraw

from snowfall.graphics.cards import _canvas, _fit, _png, font, clean

MAP_POSITIONS = {
    "Los Angeles": (144, 398),
    "Las Vegas": (286, 330),
    "Chicago": (499, 288),
    "Detroit": (629, 244),
    "Philadelphia": (752, 370),
    "New York": (858, 293),
}
LABELS = {
    "Chicago": "CHI", "New York": "NYC", "Detroit": "DET",
    "Philadelphia": "PHL", "Las Vegas": "VEG", "Los Angeles": "LAX",
}


def _centre(draw, text, x, y, f, fill):
    width = draw.textlength(text, font=f)
    draw.text((int(x-width/2), y), text, font=f, fill=fill)


def _plaque(draw, bounds, fill=(13, 31, 49, 232), outline=(147, 206, 232, 153)):
    draw.rounded_rectangle(bounds, radius=15, fill=fill, outline=outline, width=2)


def _district_colour(board, city):
    if city is None:
        return "#9caab6"
    return board.banner(city).colour


def territory_map_card(board, *, highlighted_city=None) -> bytes:
    """960×540 overview with six interactive-by-select city locations."""
    day = f"DAY {board.day}/7" if board.day is not None else "AWAITING KICKOFF"
    im, d = _canvas(board.viewer_city, "SIX-CITY TERRITORY WAR",
                    f"{day}  •  NO TERRITORY PRIZES  •  SCHEMATIC MAP")
    _plaque(d, (40, 205, 920, 469), fill=(11, 27, 43, 231))
    # Original abstract game-world route map, not a factual or street-accurate map.
    d.line([(90, 411), (176, 299), (272, 292), (375, 258), (495, 224),
            (613, 228), (742, 306), (879, 282)], fill=(117, 157, 182, 100), width=3)
    d.line([(176, 299), (180, 391), (312, 399), (461, 405), (607, 397),
            (742, 411), (879, 282)], fill=(96, 137, 166, 80), width=2)
    for i in range(27):
        x = 58 + (i*137 % 838)
        y = 223 + (i*71 % 218)
        d.ellipse((x, y, x+2, y+2), fill=(220, 238, 248, 145))
    # Current day's daily opponent links and both fictional frontier controls.
    for match in board.matches:
        a, b = MAP_POSITIONS[match.city_a], MAP_POSITIONS[match.city_b]
        edge = _district_colour(board, match.rally_owner)
        d.line((*a, *b), fill=edge, width=6 if match.rally_owner else 3)
        x, y = (a[0]+b[0])//2, (a[1]+b[1])//2
        for offset, letter, holder in [(-18, "R", match.rally_owner),
                                       (18, "D", match.duel_owner)]:
            fill = _district_colour(board, holder)
            d.ellipse((x-13, y+offset-13, x+13, y+offset+13),
                      fill=(11, 28, 45, 255), outline=fill, width=3)
            _centre(d, letter, x, y+offset-9, font(13, True), "#eef7ff")
    home = {d.contenders[0]: d.owner for d in board.districts if d.kind == "home"}
    for city, (x, y) in MAP_POSITIONS.items():
        banner = board.banner(city)
        chosen = city == highlighted_city
        owned = home.get(city) == city
        d.ellipse((x-34, y-34, x+34, y+34),
                  fill=(17, 37, 56, 252),
                  outline=banner.colour if owned else "#7892a5",
                  width=5 if chosen or owned else 3)
        if chosen:
            d.ellipse((x-40, y-40, x+40, y+40), outline="#ffffff", width=3)
        _centre(d, LABELS[city], x, y-16, font(18, True), "#f4faff")
        _centre(d, "HOME" if owned else "NEUTRAL", x, y+6, font(10, True),
                "#b0ebd0" if owned else "#bac8d5")
        _centre(d, city, x, min(442,y+41), font(13, True), "#ffffff")
    _plaque(d, (44, 479, 917, 513), fill=(13, 30, 49, 239))
    if board.matches:
        for i, match in enumerate(board.matches):
            x = 56 + i*285
            descriptor = f"{LABELS[match.city_a]} vs {LABELS[match.city_b]}  R:"
            own = LABELS[match.rally_owner] if match.rally_owner else "TIE"
            label = f"{descriptor}{own}"
            d.text((x, 486), _fit(d, label, 270, font(15, True)),
                   font=font(15, True), fill="#e5f2fc")
    else:
        d.text((67, 486), "Territories open when the seven-day event begins.",
               font=font(16, True), fill="#e4f3ff")
    return _png(im)


def city_banners_card(board) -> bytes:
    """Distinct city palettes and original illustrated heraldic emblems."""
    im, d = _canvas(board.viewer_city, "BANNERS OF THE SIX CITIES",
                    f"DAY {board.day or '—'}/7  •  CITY HONOURS ONLY")
    for index, banner in enumerate(board.banners):
        col, row = index % 2, index // 2
        x, y = 51 + 451*col, 212 + 101*row
        _plaque(d, (x, y, x+430, y+91), fill=(11, 30, 48, 237))
        d.rounded_rectangle((x+8, y+8, x+54, y+83), radius=7,
                            fill=banner.colour, outline="#f3f7ff", width=2)
        # Original geometric crest icon; no dependency on platform emoji fonts.
        d.polygon([(x+31,y+19),(x+44,y+31),(x+40,y+63),(x+31,y+74),
                   (x+22,y+63),(x+18,y+31)], fill=(15, 34, 54, 235))
        _centre(d, LABELS[banner.city][0], x+31, y+36,
                font(17, True), "#ffffff")
        d.text((x+69, y+14), _fit(d, banner.city, 304, font(23, True)),
               font=font(23, True), fill="#f2f9ff")
        d.text((x+69, y+43), _fit(d, banner.motto, 318, font(14)),
               font=font(14), fill="#c4dfe9")
        held = len(board.held(banner.city))
        d.text((x+69, y+66), f"{held} districts  ·  {banner.active} active  ·  "
               f"{banner.rally_marks} rally marks", font=font(12, True), fill="#ffe5b5")
    return _png(im)


def city_territory_card(board, city: str) -> bytes:
    banner = board.banner(city)
    im, d = _canvas(city, f"{city.upper()} WAR ROOM",
                    f"{banner.motto.upper()}  •  {banner.home_district}")
    _plaque(d, (54, 220, 592, 442))
    owned = board.held(city)
    d.text((77, 239), "HONORARY DISTRICT CONTROL", font=font(19, True), fill="#d4eafb")
    d.text((77, 277), f"{len(owned)} / 12", font=font(49, True), fill=banner.colour)
    d.text((80, 351), f"RALLY MARKS: {banner.rally_marks}",
           font=font(21, True), fill="#ffe1a8")
    d.text((80, 384), f"ACTIVE MEMBERS: {banner.active}/{banner.registered}",
           font=font(19, True), fill="#d9ebf8")
    _plaque(d, (618, 220, 909, 442), fill=(16, 33, 52, 235))
    d.rounded_rectangle((703, 249, 824, 398), radius=10,
                        fill=banner.colour, outline="#ffffff", width=3)
    d.polygon([(763,264),(802,287),(792,354),(763,384),
               (735,354),(725,287)], fill="#172d43")
    _centre(d, LABELS[city], 763, 313, font(25, True), "#ffffff")
    d.text((60, 467), _fit(d, ("CLAIMED: " + ", ".join(x.name for x in owned))
                         if owned else "NO DISTRICTS CLAIMED YET", 810, font(16, True)),
           font=font(16, True), fill="#e2effa")
    d.text((60, 499), "HONORARY CONTROL ONLY • NO EXTRA POINTS OR PRIZES",
           font=font(13, True), fill="#b7d7ea")
    return _png(im)
