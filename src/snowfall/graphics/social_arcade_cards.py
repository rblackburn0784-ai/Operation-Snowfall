"""Original locally rendered 960×540 winter arcade game, leaderboard and passport art."""
from __future__ import annotations

from snowfall.graphics.cards import _canvas, _png, _fit, font
from snowfall.services.social_arcade import STAMPS


def _panel(draw, bounds, title, value=None, *, tint="#b8e9f6"):
    x1,y1,x2,y2 = bounds
    draw.rounded_rectangle(bounds, radius=16,
                           fill=(13, 30, 47, 231), outline=(149, 193, 209, 145),
                           width=2)
    draw.text((x1+15,y1+12), _fit(draw,title,x2-x1-28,font(19,True)),
              font=font(19,True),fill=tint)
    if value is not None:
        draw.text((x1+15,y1+46),_fit(draw,str(value),x2-x1-28,font(23,True)),
                  font=font(23,True), fill="#f6faff")


def lobby_card(lobby, city="Chicago") -> bytes:
    im,d=_canvas(city,"THE WINTER ARCADE",
                 f"DAY {lobby.day or '—'}/7  •  FIVE GAMES  •  NO PAID PRIZES")
    for i,record in enumerate(lobby.records):
        x=48+(i%2)*452
        y=217+(i//2)*91
        _panel(d,(x,y,x+432,y+82),record.name,
               f"BEST {record.personal_best}/100  ·  TODAY {record.attempts_today}/3",
               tint="#ffe3b4" if i%2 else "#b3e5f8")
    d.text((510,486),f"TOUR {lobby.completed} RUNS  ·  {len(lobby.stamps)} STAMPS",
           font=font(16,True),fill="#ffe4ac")
    return _png(im)


def game_card(session, city="Chicago") -> bytes:
    im,d=_canvas(city,session.title.upper(),
                 f"DAY {session.day}/7  •  RUN {session.attempt}/3  •  {session.score}/100")
    d.rounded_rectangle((49,212,914,468),radius=19,
                        fill=(13,29,46,234),outline=(164,216,238,141),width=3)
    width=834
    prog=int(width * session.step / max(1,session.total_rounds))
    d.rounded_rectangle((64,230,896,247),radius=8,fill=(53,69,81,240))
    if prog:
        d.rounded_rectangle((64,230,64+prog,247),radius=8,fill="#a7ebd3")
    d.text((75,263),
           f"{'GAME COMPLETE' if session.finished else f'ROUND {session.step+1}/{session.total_rounds}'}",
           font=font(25,True),fill="#ffe0a0")
    if session.current:
        # Render original arcade illustration by game mechanic.
        mode=session.mode
        if mode=="gallery":
            for x in (143,288,433):
                d.ellipse((x,328,x+83,411),fill="#cfeaf2",outline="#ca6f76",width=12)
                d.ellipse((x+23,351,x+60,388),fill="#4c8caa")
            d.text((633,348),"AIM",font=font(46,True),fill="#ffdca9")
        elif mode=="safe":
            for x in (136,278,420):
                d.ellipse((x,321,x+103,424),fill="#718c9f",outline="#d9e9ef",width=7)
                d.ellipse((x+25,345,x+78,397),fill="#172b3c",outline="#ffd8a2",width=3)
            d.text((639,347),"LOCKED",font=font(29,True),fill="#f4d9a5")
        elif mode=="snowman":
            d.ellipse((270,355,406,452),fill="#eaf6fc")
            d.ellipse((291,303,384,378),fill="#f3fbfe")
            d.ellipse((306,275,368,333),fill="#ffffff")
            d.rectangle((304,277,368,286),fill="#243952")
            d.rectangle((321,243,351,283),fill="#243952")
            d.line((267,361,208,337),fill="#b7a17d",width=8)
            d.line((408,360,463,332),fill="#b7a17d",width=8)
            d.text((621,350),"BUILD",font=font(40,True),fill="#daeeff")
        elif mode=="catch":
            for x in (185,385,585):
                d.line((x,323,x,427),fill="#547997",width=3)
                d.ellipse((x-28,342,x+28,398),outline="#c0f0ff",width=7)
                d.line((x-36,370,x+36,370),fill="#add7f1",width=4)
            d.text((692,352),"CATCH",font=font(25,True),fill="#e5d99d")
        else:
            d.ellipse((334,309,481,451),fill="#31526e",outline="#eed58e",width=5)
            d.text((374,330), "?",font=font(88,True),fill="#fff0bf")
            d.text((585,350),"TRIVIA",font=font(31,True),fill="#ffe9ad")
    else:
        d.text((127,325), f"FINAL ARCADE SCORE: {session.score} / 100",
               font=font(36,True),fill="#ffe2a4")
    d.text((58,490),"CASUAL RECORDS ONLY  •  ALL COMPETITION PRIZES UNCHANGED",
           font=font(16,True),fill="#d1e7f0")
    return _png(im)


def passport_card(lobby, city="Chicago") -> bytes:
    im,d=_canvas(city,"WINTER ARCADE PASSPORT",
                 f"{len(lobby.stamps)}/{len(STAMPS)} COLLECTIBLE STAMPS • DECORATIVE ONLY")
    for i,(key,name) in enumerate(STAMPS.items()):
        x=48+(i%2)*455
        y=205+(i//2)*47
        unlocked=key in lobby.stamps
        d.rounded_rectangle((x,y,x+436,y+42),radius=12,
                            fill=(16,51,48,231) if unlocked else (14,29,46,230),
                            outline=(116,219,179,200) if unlocked else (111,148,175,145),
                            width=2)
        title=name.replace("🎯 ","").replace("🔐 ","").replace("☃️ ","").replace(
            "❄️ ","").replace("🎄 ","").replace("🏅 ","").replace("🌟 ","")
        d.text((x+13,y+9), "★" if unlocked else "·",
               font=font(20,True),fill="#f3d28b" if unlocked else "#819daf")
        d.text((x+47,y+12),_fit(d,title,368,font(14,True)),
               font=font(14,True),fill="#e3f7ef" if unlocked else "#8faaba")
    d.text((55,514),"PLAY FOR FUN • NO BONUS POINTS, SNOWFLAKES, ITEMS OR PRIZES",
           font=font(13,True),fill="#d7e7ef")
    return _png(im)


def scoreboard_card(title, rows, city="Chicago") -> bytes:
    im,d=_canvas(city,"ARCADE HIGH-SCORE BOARD",
                 title.upper() + "  •  HONORARY RECORDS ONLY")
    for i,row in enumerate(rows[:8]):
        y=217+i*36
        d.rounded_rectangle((67,y,892,y+32),radius=8,
                            fill=(17,37,55,232),outline=(132,175,196,80))
        label=f"{i+1:>2}. {getattr(row,'name',getattr(row,'city','Unknown'))}"
        value=getattr(row,'best',getattr(row,'score',0))
        d.text((82,y+5),_fit(d,label,642,font(16,True)),font=font(16,True),
               fill="#f7e8bc" if i==0 else "#e1f2fa")
        d.text((780,y+5),str(value),font=font(17,True),fill="#c8ecda")
    if not rows:
        d.text((115,300),"NO COMPLETED GAMES YET — THE ARCADE IS OPEN!",
               font=font(24,True),fill="#d6eaf4")
    return _png(im)
