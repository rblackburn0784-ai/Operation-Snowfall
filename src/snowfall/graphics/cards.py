"""Snowfall's Pillow graphics; deterministic presentation with no gameplay side effects.

Images are original locally packaged assets. Never depend on a network request or
mutate the database here. Every card can render without its optional artwork.
"""
from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Iterable
import math

from PIL import Image, ImageDraw, ImageFont

from snowfall.graphics.snow_don import draw_portrait

WIDTH, HEIGHT = 960, 540
ART = Path(__file__).resolve().parent / "art"
CITIES = ("Chicago", "New York", "Detroit", "Philadelphia", "Las Vegas", "Los Angeles")
CITY_COLOURS = {
    "Chicago": "#ec6f70", "New York": "#74aee6", "Detroit": "#bd9ee7",
    "Philadelphia": "#ffd084", "Las Vegas": "#ec99d9", "Los Angeles": "#91dcba",
}


@lru_cache(maxsize=12)
def font(size: int, bold: bool = False):
    names = (
        ["DejaVuSans-Bold.ttf", "C:/Windows/Fonts/arialbd.ttf"] if bold else
        ["DejaVuSans.ttf", "C:/Windows/Fonts/arial.ttf"]
    )
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def clean(value: object, limit=64) -> str:
    """Render names as text, not markup. No mentions, mass pings, or multiline art."""
    return " ".join(str(value or "—").split())[:limit] or "—"


def _fit(draw: ImageDraw.ImageDraw, value, width: int, face):
    name = clean(value, 160)
    if draw.textlength(name, font=face) <= width:
        return name
    while name and draw.textlength(name + "…", font=face) > width:
        name = name[:-1]
    return name + "…"


def _background(city: str) -> Image.Image:
    try:
        if city in CITIES:
            path = ART / "cities" / (city.lower().replace(" ", "_") + ".webp")
            with Image.open(path) as image:
                return image.convert("RGB").resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    except (OSError, ValueError):
        pass
    # Missing artwork is never a reason for gameplay to fail.
    image = Image.new("RGB", (WIDTH, HEIGHT))
    d = ImageDraw.Draw(image)
    for y in range(HEIGHT):
        t = y / HEIGHT
        d.line((0, y, WIDTH, y), fill=(int(10 + t * 17), int(26 + t * 34), int(49 + t * 45)))
    return image


def _canvas(city: str, header: str, subhead: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    im = _background(city).convert("RGBA")
    mask = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    m = ImageDraw.Draw(mask)
    for x in range(WIDTH):
        alpha = round(222 - 85 * (x / WIDTH) ** 1.35)
        m.line((x, 0, x, HEIGHT), fill=(7, 17, 32, alpha))
    m.rounded_rectangle((28, 23, 930, 515), radius=25,
                        outline=(219, 238, 250, 95), width=2)
    im = Image.alpha_composite(im, mask)
    d = ImageDraw.Draw(im)
    d.text((52, 47), "OPERATION SNOWFALL", font=font(20, True), fill="#a9dff8")
    d.text((52, 89), _fit(d, header, 824, font(43, True)),
           font=font(43, True), fill="white")
    d.text((53, 151), _fit(d, subhead, 820, font(23)),
           font=font(23), fill="#cadfed")
    d.line((53, 191, 901, 191), fill=(205, 236, 253, 95), width=2)
    return im, d


def _panel(d, box, label, value, *, colour="#f2f9ff"):
    d.rounded_rectangle(box, radius=17, fill=(12, 26, 44, 207), outline=(162, 210, 240, 82), width=2)
    x, y, right, bottom = box
    d.text((x + 18, y + 13), label.upper(), font=font(16, True), fill="#b6d5e7")
    d.text((x + 18, y + 47), _fit(d, value, right - x - 33, font(29, True)),
           font=font(29, True), fill=colour)


def _bar(d, box, current: int, maximum: int, label: str, colour):
    x,y,r,b=box
    ratio = max(0.,min(1.,float(current)/max(1,float(maximum))))
    d.text((x,y),f"{label.upper()}  {int(current)} / {int(maximum)}",font=font(17,True),fill="#eaf5ff")
    y+=34
    d.rounded_rectangle((x,y,r,y+18),radius=9,fill="#152b43")
    if ratio>0:
        fillw=max(14,int((r-x)*ratio))
        d.rounded_rectangle((x,y,x+min(r-x,fillw),y+18),radius=9,fill=colour)


def _icon(im: Image.Image, key: str, xy: tuple[int,int], size=120):
    try:
        with Image.open(ART/"items"/(key+".png")) as asset:
            icon=asset.convert("RGBA").resize((size,size),Image.Resampling.LANCZOS)
            im.alpha_composite(icon,xy)
    except (OSError,ValueError):
        pass


def _png(im: Image.Image) -> bytes:
    out = BytesIO()
    im.convert("RGB").save(out, format="PNG", optimize=True)
    return out.getvalue()


def profile_card(name, city, resource, total, *, review="self-declared") -> bytes:
    im,d=_canvas(city,"PLAYER PROFILE",f"{clean(name,42)}  •  {clean(city)}  •  {clean(review)}")
    _bar(d,(55,230,540,280),resource.warmth,100,"Warmth","#ed8684")
    _bar(d,(55,314,540,362),resource.snowballs,12,"Snowballs","#8bd8fb")
    _bar(d,(55,396,540,444),resource.today_pvp,300,"Daily PvP","#b4e6b9")
    _panel(d,(575,224,898,332),"Season points",str(total),colour="#ffdba2")
    _panel(d,(575,345,898,457),"Snowflakes",str(resource.snowflakes),colour="#a3defd")
    d.text((57,484),"YOUR SEASON • PERSONAL REWARDS ONLY",font=font(15,True),fill="#c1d2dd")
    return _png(im)


def battle_card(result, target: str, attacker: str="YOUR THROW") -> bytes:
    city=clean(getattr(result,"target_city","Chicago"))
    im,d=_canvas(city, "KNOCKOUT!" if result.knocked_out else
                 ("CRITICAL HIT!" if result.critical else ("DIRECT HIT!" if result.hit else "SNOWBALL MISSED")),
                 f"{clean(attacker,24)}  vs  {clean(target,38)}")
    _icon(im,"golden" if result.style=="golden" else "snowball",(700,211),160)
    _panel(d,(53,228,270,342),"Warmth damage",str(result.warmth_damage),colour="#f0a3a4")
    _panel(d,(291,228,508,342),"Fort absorbed",str(result.armour_damage))
    _panel(d,(53,356,270,468),"Points gained",f"+{result.points_awarded}",colour="#c3edba")
    _panel(d,(291,356,508,468),"Throw style",result.style.title())
    d.text((570,469),"30-SECOND COOLDOWN",font=font(17,True),fill="#d5eafd")
    return _png(im)


def world_status_card(state) -> bytes:
    im,d=_canvas(state.city,"WINTER WARZONE",f"Day {state.day or '—'} / 7  •  {clean(state.theme)}")
    # The image follows the same authoritative shared HP used by the bar.
    # Transparent art occupies the right panel; missing artwork uses old icon.
    stage = draw_portrait(im, state.boss_hp, state.boss_max_hp, (650, 186, 923, 485))
    if stage is None:
        _icon(im, "boss", (730, 210), 125)
    else:
        d.rounded_rectangle((698, 471, 903, 505), radius=12, fill=(8, 22, 40, 225))
        d.text((713, 477), "DEFEATED" if state.boss_hp <= 0 else f"SNOW DON • {stage}% HP",
               font=font(16, True), fill="#e0f3ff")
    _bar(d,(55,229,617,277),state.boss_hp,max(1,state.boss_max_hp),"Snow Don","#a9d6f4")
    _bar(d,(55,332,617,382),state.siege_hp,max(1,state.siege_max_hp),
         f"{clean(state.city)} fortress","#f2ca8c")
    d.text((57,437),f"BOSS {state.boss_attempts}/6  •  SIEGE {state.siege_attempts}/4 ATTEMPTS",
           font=font(20,True),fill="white")
    d.text((57,484),"ONE SNOWBALL • 30s SHARED COOLDOWN",font=font(16),fill="#d7eaf9")
    return _png(im)


def world_result_card(result) -> bytes:
    city=getattr(result,"city", "Chicago")
    is_boss=result.kind=="boss"
    title="FINAL BLOW!" if result.final_blow else ("NICE HIT!" if result.hit else "MISS!")
    im,d=_canvas(city,title,
        f"Day {result.day}  •  {'Snow Don' if is_boss else clean(city)+' Fortress'}"
        + ("  •  Training echo" if result.echo else ""))
    if is_boss:
        stage = draw_portrait(im, result.hp_after, result.max_hp, (637, 192, 925, 478))
        if stage is None:
            _icon(im, "boss", (710, 214), 165)
        else:
            d.rounded_rectangle((697, 456, 910, 493), radius=12, fill=(8, 22, 40, 225))
            d.text((711, 464), "DEFEATED" if result.hp_after <= 0 else f"SNOW DON • {stage}% HP",
                   font=font(16, True), fill="#e0f3ff")
    else:
        _icon(im, "siege", (710, 214), 165)
    _panel(d,(55,224,305,335),"Damage dealt",str(result.damage))
    _panel(d,(323,224,575,335),"Your points",f"+{result.points}",colour="#c7efa9")
    _bar(d,(55,372,574,426),result.hp_after,max(1,result.max_hp),"Shared HP","#afd9f6")
    d.text((57,477),"LATE PLAYERS CAN STILL EARN ECHO POINTS",font=font(14,True),fill="#d5e6f1")
    return _png(im)


def champions_card(players: Iterable, cities: Iterable, *, final: bool=False) -> bytes:
    leaders=list(players)[:3]
    city_rows=list(cities)
    winner=city_rows[0].city if city_rows else "Chicago"
    im,d=_canvas(winner,"SNOWFALL CHAMPIONS",
                 "FINAL STANDINGS • STAFF REVIEW PENDING" if final else "PROVISIONAL STANDINGS • NOT PRIZE RESULTS")
    _icon(im,"golden",(723,207),170)
    names=[(str(row[0]),int(row[3])) for row in leaders]
    for idx in range(3):
        x=55+idx*218
        title=("1ST","2ND","3RD")[idx]
        if idx < len(names):
            name, score = names[idx]
        else:
            name, score = "—", 0
        _panel(d,(x,224,x+198,340),title,_fit(d,name,165,font(22,True)),colour="#ffdb98" if idx==0 else "#f3f7ff")
        d.text((x+16,350),f"{score} points",font=font(20,True),fill="#d3eafa")
    d.rounded_rectangle((55,404,672,483),radius=15,fill=(12,28,45,218))
    d.text((75,413),"HONORARY CITY CHAMPION",font=font(15,True),fill="#c0d7ec")
    d.text((75,443),_fit(d,winner,540,font(27,True)),font=font(27,True),fill="#ffe2a4")
    return _png(im)


def hit_animation(result, target: str, *, maximum_bytes=4_000_000) -> bytes | None:
    """Small original GIF effect, no external files beyond our own static battle card."""
    if not (result.hit and (result.critical or result.knocked_out)):
        return None
    with Image.open(BytesIO(battle_card(result,target))) as picture:
        base=picture.resize((480,270),Image.Resampling.BILINEAR).convert("RGB")
    frames=[]
    for i in range(9):
        frame=base.copy().convert("RGBA")
        a=Image.new("RGBA",(480,270),(0,0,0,0))
        d=ImageDraw.Draw(a)
        x=int(42+(i/8)*340)
        y=int(215-93*math.sin(math.pi*i/8))
        rad=13 if i<7 else 20+(i-7)*10
        d.ellipse((x-rad,y-rad,x+rad,y+rad),fill=(224,249,255,255),outline=(111,184,231,255),width=3)
        if i>=7:
            for k in range(6):
                angle=math.pi*k/3
                cx=x+int(29*math.cos(angle))
                cy=y+int(29*math.sin(angle))
                d.ellipse((cx-4,cy-4,cx+4,cy+4),fill=(255,233,160,220))
        frame=Image.alpha_composite(frame,a).convert("RGB")
        frames.append(frame.quantize(colors=80,method=Image.Quantize.MEDIANCUT))
    out=BytesIO()
    frames[0].save(out,format="GIF",save_all=True,append_images=frames[1:],
                                duration=130,loop=0,optimize=True,disposal=2)
    data=out.getvalue()
    return data if len(data)<maximum_bytes else None


def world_animation(result, *, maximum_bytes=4_000_000) -> bytes | None:
    """Original, short celebration GIF for a Snow Don or fortress final blow."""
    if not result.final_blow:
        return None
    with Image.open(BytesIO(world_result_card(result))) as picture:
        base = picture.resize((480,270),Image.Resampling.BILINEAR).convert("RGB")
    frames=[]
    for i in range(9):
        im=base.copy()
        d=ImageDraw.Draw(im,"RGBA")
        for k in range(12):
            angle=2*math.pi*k/12+i*.12
            radius=12+i*10
            x=int(332+radius*math.cos(angle))
            y=int(127+radius*math.sin(angle))
            size=4+(k%3)
            d.ellipse((x-size,y-size,x+size,y+size),fill=(255,226,126,max(50,220-i*17)))
        frames.append(im.quantize(colors=80,method=Image.Quantize.MEDIANCUT))
    out=BytesIO()
    frames[0].save(out,format="GIF",save_all=True,append_images=frames[1:],
                                duration=140,loop=0,optimize=True,disposal=2)
    data=out.getvalue()
    return data if len(data)<maximum_bytes else None
