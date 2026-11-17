"""Original Snow Don raid artwork, damage-phase transitions and final cinematic.

All images render locally from the existing ten transparent Snow Don portraits.
These functions are deliberately pure and may fail safely without affecting HP,
awards or the saved event. GIFs are intentionally mobile/Discord sized.
"""
from __future__ import annotations

from dataclasses import replace
from io import BytesIO
import math
import random

from PIL import Image, ImageDraw

from snowfall.graphics.cards import (
    _canvas, _fit, _png, _bar, _panel, clean, font, world_result_card,
)
from snowfall.graphics.snow_don import draw_portrait
from snowfall.services.boss_personality import phase_transitions


def raid_board_card(report, *, viewer_id: int | None = None, city: str = "Chicago") -> bytes:
    """Illustrated, private 960×540 raid dashboard, including cooperative totals."""
    im, d = _canvas(city, "THE DON'S RAID ROOM",
                    f"DAY {report.day}/7  •  {report.phase.upper()}  •  HONORARY RAID RECORDS")
    stage = draw_portrait(im, report.remaining_hp, report.max_hp, (676, 200, 924, 468))
    if stage is None:
        from snowfall.graphics.cards import _icon
        _icon(im, "boss", (710, 229), 155)
    d.rounded_rectangle((692, 476, 917, 505), radius=9, fill=(13, 30, 48, 225))
    d.text((706, 479), "DON DEFEATED" if report.defeated else
           f"SNOW DON · {stage or 100}% HP PORTRAIT",
           font=font(14, True), fill="#ffe4bb")
    if not report.enabled:
        d.text((52, 228), "THE SNOW DON IS DISABLED", font=font(24, True), fill="#ffe9c5")
        d.text((52, 264), "No raid honours are available for this boss.",
               font=font(17), fill="#dce6f2")
        return _png(im)
    _bar(d, (51, 214, 627, 257), report.remaining_hp, max(1, report.max_hp),
         "Shared Boss HP", "#a6d6fb")
    _panel(d, (51, 302, 222, 401), "Raiders", str(report.contributors))
    _panel(d, (235, 302, 429, 401), "Shared hits", str(report.hit_count))
    _panel(d, (441, 302, 627, 401), "Damage", str(report.shared_damage))
    d.text((52, 427), f"RAID MILESTONES: {', '.join(str(n) + '%' for n in report.milestones) or 'NONE YET'}",
           font=font(16, True), fill="#d8ebfc")
    next_goal = f"{report.next_milestone}% NEXT" if report.next_milestone else "ALL COMPLETE"
    d.text((52, 455), f"CO-OP PROGRESS  {report.progress}%  ·  {next_goal}",
           font=font(16, True), fill="#ffe3af")
    user = report.member(viewer_id) if viewer_id is not None else None
    if user:
        d.text((52, 483), _fit(d,
               f"YOU: {user.shared_damage} SHARED DAMAGE  ·  {user.shared_hits} HITS  ·  "
               f"{user.echo_attacks} ECHO DRILLS", 570, font(14, True)),
               font=font(14, True), fill="#b9e1fa")
    else:
        d.text((52, 483), "RAID HONOURS ARE COSMETIC • NO BONUS PRIZES",
               font=font(14, True), fill="#b9e1fa")
    return _png(im)


def raid_leaders_card(report, *, city="Chicago") -> bytes:
    im, d = _canvas(city, f"RAIDERS OF DAY {report.day}",
                    "COOPERATIVE RANKINGS  •  NO ADDITIONAL SCORES OR PRIZES")
    leaders = report.members[:4]
    for index in range(4):
        y = 224 + 68 * index
        d.rounded_rectangle((52, y, 907, y + 58), radius=10,
                            fill=(10, 27, 45, 218), outline=(143, 196, 230, 155), width=2)
        if index >= len(leaders):
            d.text((71, y + 17), f"{index+1}.  WAITING FOR A RAIDER",
                   font=font(18, True), fill="#89aebf")
            continue
        entry = leaders[index]
        label = _fit(d, f"{index+1}. {clean(entry.name)} • {clean(entry.city)}",
                     510, font(20, True))
        d.text((70, y + 16), label, font=font(20, True), fill="#edf7fb")
        d.text((606, y + 17), f"{entry.shared_damage} DMG  •  {entry.shared_hits} HITS",
               font=font(15, True), fill="#ffe4ae")
    d.text((55, 506), f"SHARED DAMAGE {report.shared_damage}/{report.max_hp}  ·  "
           f"CONTRIBUTORS {report.contributors}", font=font(13, True), fill="#d8e8f3")
    return _png(im)


def _gif(frames: list[Image.Image], durations: list[int], *, maximum_bytes: int) -> bytes | None:
    if not frames:
        return None
    out = BytesIO()
    frames[0].save(out, format="GIF", save_all=True, append_images=frames[1:],
                   duration=durations, disposal=2, loop=0, optimize=True)
    data = out.getvalue()
    return data if len(data) < maximum_bytes else None


def _frame(png: bytes) -> Image.Image:
    with Image.open(BytesIO(png)) as source:
        return source.convert("RGB").resize((480, 270), Image.Resampling.BILINEAR)


def phase_transition_animation(result, *, maximum_bytes=4_000_000) -> bytes | None:
    """Short real portrait-change animation only on a fresh phase-crossing hit."""
    phases = phase_transitions(result)
    if not phases:
        return None
    before = min(result.max_hp, result.hp_after + result.damage)
    previous = _frame(world_result_card(replace(
        result, hp_after=before, final_blow=False)))
    after = _frame(world_result_card(result))
    frames = []
    for index in range(9):
        image = previous.copy() if index < 4 else after.copy()
        d = ImageDraw.Draw(image, "RGBA")
        if index in (3, 4, 5):
            d.rectangle((0, 0, 480, 270), fill=(211, 246, 255, 125 - abs(4-index)*45))
        d.rounded_rectangle((272, 15, 468, 58), radius=9, fill=(12, 30, 51, 231),
                            outline=(178, 232, 253, 255), width=2)
        d.text((287, 22), f"PHASE {phases[-1]}% REACHED", font=font(15, True),
               fill="#ffe2a4")
        # Distinct moving snow-particle per frame keeps the full storyboard
        # instead of GIF optimizers coalescing identical portrait frames.
        x = 100 + index * 29
        d.ellipse((x, 211, x + 7, 218), fill=(242, 249, 255, 255))
        frames.append(image.quantize(colors=96, method=Image.Quantize.MEDIANCUT))
    return _gif(frames, [145]*8+[750], maximum_bytes=maximum_bytes)


def final_defeat_cinematic(result, *, maximum_bytes=4_000_000) -> bytes | None:
    """16-scene illustrated Snow Don finale; one unique stored real final hit.

    Starts from the pre-final wounded portrait, transitions to 0-HP artwork,
    bursts into ice particles, then holds a gold cinematic victory title.
    Never plays on training echoes, sieges or repeated interaction IDs.
    """
    if (result.kind != "boss" or not result.final_blow
            or result.echo or result.repeated):
        return None
    before = min(result.max_hp, result.hp_after + result.damage)
    wounded = _frame(world_result_card(replace(
        result, hp_after=before, final_blow=False)))
    defeated = _frame(world_result_card(result))
    rand = random.Random(f"snow-don-finale:{result.day}:{result.interaction_id}")
    flakes = [(rand.randrange(75, 466), rand.randrange(10, 256),
               rand.randint(2, 6)) for _ in range(58)]
    frames = []
    for idx in range(16):
        frame = (wounded.copy() if idx < 5 else defeated.copy())
        d = ImageDraw.Draw(frame, "RGBA")
        if 5 <= idx <= 8:
            fade = (160, 230, 255, max(0, 205 - abs(6-idx)*58))
            d.rectangle((0, 0, 480, 270), fill=fade)
        if 4 <= idx <= 11:
            energy = idx - 4
            for k in range(8):
                angle = math.pi * k / 4
                d.line((378, 164,
                        378+int((13+energy*22)*math.cos(angle)),
                        164+int((13+energy*22)*math.sin(angle))),
                       fill=(202, 246, 255, max(40, 230-energy*25)), width=3)
        if idx >= 7:
            for n, (x, y, radius) in enumerate(flakes):
                if n % 4 > idx % 5 and idx < 11:
                    continue
                px = max(1, min(478, x+int((idx-7)*((n % 7)-3)*2)))
                py = max(1, min(268, y+int((idx-7)*((n % 5)-2)*3)))
                gold = (255, 220, 140, 240) if n % 4 == 0 else (194, 243, 255, 240)
                d.ellipse((px-radius, py-radius, px+radius, py+radius), fill=gold)
        if idx >= 10:
            d.rounded_rectangle((17, 189, 463, 259), radius=11,
                                fill=(30, 26, 37, 243),
                                outline=(255, 218, 135, 251), width=3)
            d.text((41, 201), "THE SNOW DON HAS FALLEN!", font=font(21, True),
                   fill="#ffe4aa")
            d.text((47, 232), "ALL RAIDERS SHARE THE VICTORY",
                   font=font(13, True), fill="#deedf6")
        x = 34 + idx * 19
        d.ellipse((x, 73, x + 9, 82), fill=(255, 249, 216, 255))
        frames.append(frame.quantize(colors=112, method=Image.Quantize.MEDIANCUT))
    return _gif(frames, [130]*5+[110]*6+[140]*4+[1000],
                maximum_bytes=maximum_bytes)
