"""v0.2.8 original 960x540 illustrated 1930s-noir newspaper and radio flash cards."""
from __future__ import annotations

from PIL import Image, ImageDraw

from snowfall.graphics.cards import _background, _fit, _png, font
from snowfall.services.wire import clean_name


def _newspaper(city: str):
    canvas=_background(city).convert("RGBA")
    veil=Image.new("RGBA",canvas.size,(12,14,24,218))
    canvas=Image.alpha_composite(canvas,veil)
    d=ImageDraw.Draw(canvas,"RGBA")
    d.rounded_rectangle((27,19,932,518),radius=15,
                        fill=(232,224,197,245),outline=(146,105,66,255),width=4)
    for x in (342,652):
        d.line((x,170,x,492),fill=(166,148,120,205),width=2)
    d.rectangle((49,42,912,88),fill=(32,36,43,255))
    d.text((70,48),"THE SNOWFALL WIRE",font=font(32,True),fill="#f5eddb")
    d.text((693,59),"EST. CHRISTMAS 2026",font=font(14,True),fill="#e3cd9d")
    d.line((49,99,909,99),fill=(55,41,37,255),width=3)
    return canvas,d


def edition_card(issue)->bytes:
    im,d=_newspaper(issue.busy_city or issue.top_city or "Chicago")
    dark="#262e3b"
    d.text((55,112),f"EDITION NO. {issue.day:02d}  •  "
           +("MORNING EDITION" if issue.completed else "STREET EDITION"),
           font=font(16,True),fill="#72573e")
    d.text((53,139),_fit(d,issue.headline,855,font(32,True)),
           font=font(32,True),fill=dark)
    d.line((52,185,911,185),fill=(56,48,43,255),width=3)
    d.text((62,207),"TOP OF THE RACKET",font=font(16,True),fill="#624533")
    d.text((62,247),_fit(d,clean_name(issue.top_player or "NO SCORERS",30),
           259,font(24,True)),font=font(24,True),fill=dark)
    d.text((62,288),f"{issue.top_points} DAY POINTS",font=font(17,True),fill="#855837")
    d.text((62,345),"BUSIEST STREETS",font=font(16,True),fill="#624533")
    d.text((62,388),_fit(d,issue.busy_city or "QUIET STREETS",253,font(23,True)),
           font=font(23,True),fill=dark)
    d.text((62,433),f"{issue.busy_activity} LEDGER ENTRIES",
           font=font(14,True),fill="#6b5746")
    d.text((368,211),"STREET REPORT",font=font(16,True),fill="#624533")
    for i,line in enumerate((
        f"{issue.active_people} ACTIVE SCORERS",
        f"{issue.throws} THROWS / {issue.hits} HITS",
        f"{issue.boss_damage} SNOW DON DAMAGE",
        f"{issue.sieges_cleared} CITY SIEGES CLEARED",
        f"{issue.quests} QUESTS CLAIMED",
        f"{issue.presents} MYSTERY PRESENTS",
    )):
        y=254+i*36
        d.text((367,y),_fit(d,line,274,font(16,True)),
               font=font(16,True),fill=dark)
    d.text((678,211),"BACKROOM WHISPERS",font=font(16,True),fill="#624533")
    d.text((680,261),f"{issue.cases_solved} CASES SOLVED",
           font=font(18,True),fill=dark)
    d.text((680,298),f"{issue.arcade_runs} ARCADE RUNS",
           font=font(18,True),fill=dark)
    d.text((680,358),"PLAYER DISPATCHES",font=font(15,True),fill="#624533")
    d.text((681,402),f"{len(issue.stories)} PUBLISHED",
           font=font(22,True),fill=dark)
    d.line((53,491,910,491),fill=(56,48,43,255),width=2)
    d.text((62,499),"FICTIONAL EVENTS ONLY • VERIFIED GAME LOGS • NO NEW PRIZES",
           font=font(13,True),fill="#634935")
    return _png(im)


def flash_card(day:int,title:str,quantity:int=0)->bytes:
    im,d=_newspaper("Chicago")
    d.rectangle((70,136,885,192),fill=(72,42,41,249))
    d.text((88,147),f"EXTRA! EXTRA!  •  FLASH BULLETIN  •  DAY {day}/7",
           font=font(23,True),fill="#fbefda")
    d.text((90,238),_fit(d,title,772,font(32,True)),
           font=font(32,True),fill="#252c38")
    d.text((108,349),str(quantity),font=font(76,True),fill="#9d5c3f")
    d.text((291,396),"RECORDED COMMUNITY ACTIONS",font=font(20,True),fill="#4b3a36")
    d.text((83,483),"HONORARY NEWSFLASH • PLAYER PRIZES UNCHANGED",
           font=font(14,True),fill="#7c4d38")
    return _png(im)
