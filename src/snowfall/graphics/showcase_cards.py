"""Pillow-only v0.2.2 collectible card renderer.

Art is procedurally illustrated: no third-party photos, avatars, downloads or
player-provided image URLs. Cosmetic keys are allowlisted in the read model.
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

from snowfall.graphics.cards import (
    CITY_COLOURS, HEIGHT, WIDTH, _background, _bar, _fit, _png, clean, font,
)
from snowfall.services.winter_fun import COSMETICS

RARITY_COLOURS = {
    "Common": "#d2e6f0", "Rare": "#80d5ff",
    "Epic": "#d9b3ff", "Legendary": "#ffe1a1",
}

BANNER_COLOURS = {
    "midnight_banner": ((27, 28, 48, 248), "#dca7e1"),
    "aurora_banner": ((28, 59, 81, 248), "#91f2e1"),
    "gilded_banner": ((64, 44, 31, 248), "#ffdc90"),
}
FRAME_COLOURS = {
    "ice_frame": "#9de7ff", "gold_frame": "#ffd27f",
    "holly_frame": "#8ee3a0",
}


def _portrait(canvas: Image.Image, style: str, gear: str | None, trail: str | None) -> None:
    """An original full-bust winter mob character, with visibly equipped gear."""
    image = Image.new("RGBA", (290, 262), (0, 0, 0, 0))
    d = ImageDraw.Draw(image, "RGBA")
    spectre = style == "frost_spectre"
    enforcer = style == "winter_enforcer"
    detective = style == "noir_detective"
    coat = ((40, 80, 116, 255) if spectre else (91, 36, 44, 255) if enforcer
            else (87, 70, 53, 255) if detective else (39, 60, 79, 255))
    accent = ((168, 238, 255, 255) if spectre else (240, 165, 112, 255) if enforcer
              else (227, 195, 137, 255) if detective else (151, 208, 231, 255))
    skin = ((194, 227, 235, 255) if spectre else (207, 159, 127, 255)
            if enforcer else (211, 176, 143, 255))
    # Snow and cosmetic snowball trails are independent of gameplay buffs.
    if trail in ("snow_trail", "candy_trail"):
        for i in range(10):
            x = 18 + 24 * i
            y = 196 - int(97 * math.sin(math.pi * i / 11)) - 7 * (i % 3)
            col = ((169, 238, 255, 235) if trail == "snow_trail"
                   else ((255, 105, 121, 245) if i % 2 else (250, 251, 249, 255)))
            d.ellipse((x, y, x + 11, y + 11), fill=col)
            d.line((x + 5, y - 4, x + 5, y + 15), fill=col, width=2)
            d.line((x - 4, y + 5, x + 15, y + 5), fill=col, width=2)
    # Silhouette, coat lapels and lapel studs.
    d.ellipse((36, 167, 254, 352), fill=coat, outline=accent, width=3)
    d.polygon([(45, 249), (65, 154), (110, 131), (145, 171), (180, 131),
               (222, 154), (245, 249)], fill=coat)
    d.polygon([(98, 142), (143, 225), (144, 151)], fill=(13, 28, 44, 255))
    d.polygon([(193, 142), (146, 225), (144, 151)], fill=(17, 35, 53, 255))
    d.line((145, 169, 145, 257), fill=accent, width=3)
    for y in (201, 231):
        d.ellipse((153, y, 160, y + 7), fill=accent)
    # Neck and face with a subtle shadow under the brim.
    d.rounded_rectangle((130, 132, 166, 185), radius=8, fill=skin)
    d.ellipse((100, 47, 190, 173), fill=skin, outline=(52, 66, 79, 230), width=2)
    d.arc((119, 120, 171, 150), 10, 164, fill=(106, 75, 72, 255), width=2)
    d.ellipse((121, 105, 129, 111), fill=(29, 43, 53, 255))
    d.ellipse((161, 105, 169, 111), fill=(29, 43, 53, 255))
    if spectre:
        d.arc((104, 40, 188, 166), 180, 360, fill=(133, 233, 251, 220), width=5)
    # A thick fedora brim and crown, with distinctive portrait colour schemes.
    hat = ((24, 54, 75, 255) if spectre else (36, 29, 35, 255)
           if enforcer else (61, 49, 42, 255) if detective else (31, 39, 55, 255))
    d.rounded_rectangle((100, 31, 192, 96), radius=15, fill=hat, outline=accent, width=3)
    d.rectangle((102, 81, 192, 90), fill=accent)
    d.ellipse((71, 88, 217, 111), fill=hat, outline=accent, width=3)
    # Equipped arcade gear changes the actual portrait illustration.
    if gear == "goggles":
        for cx in (123, 166):
            d.ellipse((cx - 22, 95, cx + 19, 126),
                      fill=(44, 135, 176, 235), outline=(163, 246, 255, 255), width=5)
        d.line((142, 108, 147, 108), fill=(217, 251, 255, 255), width=4)
    elif gear == "scarf":
        d.arc((90, 133, 203, 207), 5, 175, fill=(245, 99, 101, 255), width=17)
        d.polygon([(173, 159), (198, 165), (213, 247), (181, 247)],
                  fill=(226, 77, 94, 255))
        for y in (207, 223, 238):
            d.line((186, y, 210, y), fill=(255, 232, 216, 245), width=3)
    elif gear == "boots":
        # Boots appear as a collector's equipment emblem next to the figure.
        d.rounded_rectangle((194, 190, 272, 252), radius=10,
                            fill=(13, 25, 46, 245), outline=(142, 210, 245, 255), width=2)
        for x in (206, 236):
            d.polygon([(x, 207), (x + 21, 207), (x + 21, 231),
                       (x + 31, 231), (x + 32, 241), (x, 241)],
                      fill=(133, 213, 251, 255), outline=(246, 251, 255, 255))
    # Crest emphasizes style even when no equipment is selected.
    d.ellipse((68, 170, 96, 198), fill=accent, outline=(252, 251, 231, 255), width=2)
    d.line((82, 175, 82, 193), fill=(15, 45, 65, 255), width=3)
    d.line((74, 184, 90, 184), fill=(15, 45, 65, 255), width=3)
    canvas.alpha_composite(image, (604, 191))


def _frame(draw: ImageDraw.ImageDraw, key: str | None) -> None:
    colour = FRAME_COLOURS.get(key, "#a5c7d7")
    width = 7 if key else 3
    draw.rounded_rectangle((599, 185, 906, 459), radius=25, outline=colour, width=width)
    if key == "ice_frame":
        for x in range(620, 900, 36):
            draw.line((x, 187, x + 8, 196), fill="#e9fdff", width=2)
            draw.line((x, 457, x + 8, 448), fill="#e9fdff", width=2)
    elif key == "gold_frame":
        for x in (612, 880):
            for y in (198, 432):
                draw.ellipse((x, y, x + 13, y + 13), fill="#fff0be",
                             outline="#f2ab56", width=2)
        draw.line((609, 200, 891, 200), fill="#ffe9b5", width=2)
    elif key == "holly_frame":
        for x in (613, 874):
            for y in (206, 427):
                draw.ellipse((x, y, x + 12, y + 12), fill="#ef7b84")
                draw.ellipse((x + 8, y - 9, x + 25, y + 4), fill="#63c789")
                draw.ellipse((x - 12, y - 7, x + 4, y + 5), fill="#83e49a")


def _banner(draw: ImageDraw.ImageDraw, banner: str | None, city: str) -> None:
    shade, trim = BANNER_COLOURS.get(banner, ((15, 34, 53, 247),
                                               CITY_COLOURS.get(city, "#a8dafa")))
    draw.rounded_rectangle((24, 21, 936, 174), radius=20,
                           fill=shade, outline=trim, width=3)
    draw.line((51, 74, 908, 74), fill=trim, width=2)
    if banner == "gilded_banner":
        for x in range(57, 900, 30):
            draw.polygon([(x, 37), (x + 7, 30), (x + 14, 37)],
                         outline="#ffe4a9")
    elif banner == "aurora_banner":
        for i in range(7):
            pts = [(420 + 65 * k, 37 + int(8 * math.sin(k + i))) for k in range(8)]
            draw.line(pts, fill=(96 + 10 * i, 194, 222, 130), width=2)
    elif banner == "midnight_banner":
        for x in range(740, 880, 17):
            draw.line((x, 27, x + 50, 65), fill=(198, 130, 177, 95), width=2)


def _medals(draw: ImageDraw.ImageDraw, featured, count: int, total: int) -> None:
    draw.text((607, 470), f"BADGES  {count}/{total}", font=font(17, True),
              fill="#e9f5fc")
    for idx in range(3):
        x = 765 + idx * 51
        if idx < len(featured):
            badge = featured[idx]
            border = RARITY_COLOURS.get(badge.rarity, "#d2e6f0")
            letters = "".join(word[0] for word in badge.badge.split()[:2]).upper()[:2]
            draw.ellipse((x, 465, x + 42, 507), fill=(25, 43, 61, 243),
                         outline=border, width=4)
            draw.text((x + 9, 474), letters or "★", font=font(16, True), fill=border)
        else:
            draw.ellipse((x, 465, x + 42, 507), fill=(15, 27, 43, 200),
                         outline="#70879a", width=2)
            draw.text((x + 15, 474), "·", font=font(18, True), fill="#70879a")


def profile_showcase_card(showcase) -> bytes:
    """960x540 original layered city card with checked inventory + earned badges."""
    city = clean(showcase.player.city)
    image = _background(city).convert("RGBA")
    dim = Image.new("RGBA", (WIDTH, HEIGHT), (4, 12, 25, 143))
    image = Image.alpha_composite(image, dim)
    d = ImageDraw.Draw(image, "RGBA")
    equipped = showcase.equipped
    banner = equipped.get("banner")
    _banner(d, banner, city)
    name = clean(showcase.player.mr_username, 42)
    d.text((51, 30), "OPERATION SNOWFALL · COLLECTOR CARD",
           font=font(18, True), fill="#e6f5ff")
    d.text((51, 79), _fit(d, name, 560, font(39, True)),
           font=font(39, True), fill="#ffffff")
    d.text((53, 130), _fit(d, f"{city}  •  {clean(showcase.title, 38)}", 630, font(21)),
           font=font(21), fill="#e2effa")
    rarity = showcase.best_rarity
    rare_colour = RARITY_COLOURS.get(rarity, "#d2e6f0")
    d.rounded_rectangle((749, 92, 910, 139), radius=16,
                        fill=(17, 29, 43, 246), outline=rare_colour, width=3)
    d.text((769, 106), f"{rarity.upper()} STYLE", font=font(16, True),
           fill=rare_colour)
    # The player card retains all canonical resource information.
    _bar(d, (53, 210, 548, 259), showcase.resources.warmth, 100,
         "Warmth", "#ef8b94")
    _bar(d, (53, 295, 548, 344), showcase.resources.snowballs, 12,
         "Snowballs", "#9bdbf5")
    _bar(d, (53, 378, 548, 429), showcase.resources.today_pvp, 300,
         "Daily PvP", "#a7e6b5")
    d.rounded_rectangle((48, 456, 566, 509), radius=13,
                        fill=(12, 28, 46, 239), outline=(159, 208, 229, 145), width=2)
    d.text((64, 466), f"SEASON  {showcase.points} PTS", font=font(17, True),
           fill="#ffe4b6")
    d.text((64, 489), f"SNOWFLAKES  {showcase.resources.snowflakes}",
           font=font(14, True), fill="#bbdff5")
    d.text((313, 468), f"WARDROBE  {showcase.owned_count}/{showcase.cosmetic_total}",
           font=font(16, True), fill="#e6f7ff")
    d.text((313, 490), "COSMETIC ONLY", font=font(13, True), fill="#b5d1e1")
    d.rounded_rectangle((601, 185, 904, 460), radius=24,
                        fill=(17, 34, 49, 229), outline=(166, 217, 240, 140), width=2)
    _portrait(image, equipped.get("portrait", "recruit"), equipped.get("gear"),
              equipped.get("trail"))
    d = ImageDraw.Draw(image, "RGBA")
    _frame(d, equipped.get("frame"))
    _medals(d, showcase.featured_badges, showcase.badge_count, showcase.badge_total)
    # Gear and trail are named on the card as well as visibly drawn in the art.
    gear = COSMETICS[equipped["gear"]].name if "gear" in equipped else "None"
    trail = COSMETICS[equipped["trail"]].name if "trail" in equipped else "None"
    d.text((615, 433), _fit(d, f"GEAR: {gear}  ·  TRAIL: {trail}", 274, font(12, True)),
           font=font(12, True), fill="#edf9ff",
           stroke_width=1, stroke_fill="#14283a")
    stamps = len(getattr(showcase, "arcade_stamps", ()))
    d.text((54, 516),
           f"ARCADE PASSPORT {stamps}/11 • NO BONUS POINTS OR PRIZES",
           font=font(12, True), fill="#d2e3ed")
    return _png(image)
