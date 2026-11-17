"""Illustrated original 1930s noir Snowfall Wire broadsheet, Pillow-only."""
from __future__ import annotations

from snowfall.graphics.cards import _canvas, _fit, _png, font


def wire_front_card(edition=None, newsroom=None, city="Chicago") -> bytes:
    day = edition.day if edition else newsroom.day if newsroom else None
    subtitle = (edition.theme if edition is not None else
                "SEVEN DAYS • SIX CITIES • ONE VERY COLD MOB")
    im,d=_canvas(city,"THE SNOWFALL WIRE",subtitle.upper())
    d.rounded_rectangle((44,208,921,509),radius=16,
                        fill=(223,211,186,245),outline=(147,110,71,255),width=4)
    d.line((65,268,899,268),fill="#685444",width=3)
    d.text((66,220),f"CHRISTMAS EDITION • DAY {day or '—'}/7",
           font=font(19,True),fill="#594032")
    d.text((66,278),_fit(d,edition.headline if edition else
          "THE STREETS ARE TALKING",788,font(34,True)),
           font=font(34,True),fill="#332d2b")
    articles=edition.verified if edition else newsroom.recent if newsroom else ()
    for i,headline in enumerate(articles[:3]):
        x=68+(i%3)*276
        d.rounded_rectangle((x,343,x+260,478),radius=8,
                            fill=(241,233,212,255),outline="#ab8d6d",width=2)
        d.text((x+10,352),_fit(d,headline.category.upper(),235,font(15,True)),
               font=font(15,True),fill="#845136")
        d.text((x+10,384),_fit(d,headline.title,234,font(17,True)),
               font=font(17,True),fill="#2c3538")
        d.text((x+10,418),_fit(d,headline.detail,231,font(13)),
               font=font(13),fill="#625751")
    return _png(im)


def wire_stories_card(stories, city="Chicago") -> bytes:
    im,d=_canvas(city,"LETTERS TO THE EDITOR",
                 "APPROVED COMMUNITY FICTION • NOT VERIFIED COMPETITION RESULTS")
    for i,story in enumerate(stories[:4]):
        y=216+i*67
        d.rounded_rectangle((56,y,911,y+59),radius=11,
                            fill=(27,37,48,235),outline=(210,174,122,155),width=2)
        d.text((75,y+7),_fit(d,f"DAY {story.day}: {story.title}",760,font(19,True)),
               font=font(19,True),fill="#ffdda3")
        d.text((75,y+34),_fit(d,f"By {story.author} of {story.city}",770,font(14)),
               font=font(14),fill="#c5e8ef")
    if not stories:
        d.text((90,330),"THE EDITOR AWAITS HIS FIRST LETTER...",
               font=font(25,True),fill="#d3e8f3")
    return _png(im)
