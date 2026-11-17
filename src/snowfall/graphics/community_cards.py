"""Original city-scene presentation cards; never affect scoring or database state."""
from __future__ import annotations

from snowfall.graphics.cards import _canvas, _bar, _panel, _png, font, _fit


def city_headquarters_card(hq) -> bytes:
    im, draw = _canvas(hq.city, "CITY HEADQUARTERS", f"{hq.city.upper()} • {hq.theme}")
    rank = f"#{hq.city_rank}" if hq.city_rank else "UNRANKED"
    _panel(draw, (54, 213, 323, 324), "City position", rank, colour="#ffd59a")
    _panel(draw, (337, 213, 609, 324), "Active today", str(hq.participants_today))
    _panel(draw, (622, 213, 900, 324), "Honorary wins", str(hq.city_wins))
    if hq.objective:
        o = hq.objective
        _bar(draw, (60, 362, 655, 405), o.progress, o.target, o.name,
             "#86e4c6" if o.completed else "#83c8f5")
        draw.text((60, 452), _fit(draw, o.detail, 580, font(19)),
                  font=font(19), fill="#dceefa")
        draw.text((668, 382), "MISSION CLEAR" if o.completed else "CITY EFFORT",
                  font=font(21, True), fill="#a9f6ce" if o.completed else "#fed8a5")
    else:
        draw.text((62, 386), "Missions unlock when the seven-day event begins.",
                  font=font(20), fill="#dfebf5")
    return _png(im)


def wire_report_card(report) -> bytes:
    city = report.leading_city or "Chicago"
    im, draw = _canvas(city, "THE SNOWFALL WIRE", f"DAY {report.day}/7 • {report.theme}")
    draw.text((60, 217), "AMERICA'S COLDEST UNDERWORLD DISPATCH", font=font(18, True),
              fill="#ffdaad")
    _panel(draw, (53, 258, 463, 375), "Top individual player",
           report.top_player or "No scoring players", colour="#ffdeae")
    _panel(draw, (485, 258, 904, 375), "Leading honorary city",
           ", ".join(report.tied_cities) or "No qualifying city")
    draw.text((58, 415), f"{report.pvp_hits} PVP HITS  •  {report.boss_damage} DON DAMAGE  •  "
              f"{report.siege_clears} FORTS CLEARED",
              font=font(20, True), fill="#e9f6ff")
    draw.text((58, 457), f"{report.quests} QUESTS  •  {report.gifts} GIFTS  •  "
              f"{len(report.city_objectives_met)} CITY MISSIONS",
              font=font(18), fill="#c9dfea")
    draw.text((59, 488), "HONORARY CITY GLORY • INDIVIDUAL PRIZES ONLY",
              font=font(14, True), fill="#d6e6ed")
    return _png(im)
