"""Optional Discord graphics transport; media errors never roll back saved gameplay."""
from __future__ import annotations

import asyncio
from io import BytesIO
import logging
import discord

from snowfall.graphics import cards

log = logging.getLogger(__name__)


def _asset(payload: bytes, filename: str, alt: str):
    return discord.File(BytesIO(payload), filename=filename, description=alt[:1024])


async def edit_result(interaction, text: str, view, renderer, *, alt: str, animate=None):
    """Edit the deferred ephemeral interaction once. On media errors, use full text."""
    try:
        picture = await asyncio.to_thread(renderer)
        filename, data = "snowfall.png", picture
        if animate is not None:
            try:
                gif = await asyncio.to_thread(animate)
                if gif:
                    filename,data="snowfall.gif",gif
            except (OSError,ValueError,MemoryError):
                log.warning("Optional GIF generation failed; using PNG",exc_info=True)
        embed=discord.Embed(colour=discord.Colour.from_rgb(114,184,218))
        embed.set_image(url=f"attachment://{filename}")
        await interaction.edit_original_response(content=text,embed=embed,view=view,
               attachments=[_asset(data,filename,alt)],allowed_mentions=discord.AllowedMentions.none())
    except (discord.HTTPException,OSError,ValueError,MemoryError) as exc:
        log.warning("Card upload failed; returning full text: %s",exc)
        await interaction.edit_original_response(content=text,embed=None,view=view,attachments=[])


async def send_profile(interaction, text, name, city, resource, total, *, review="self-declared"):
    """Use only after defer(ephemeral=True); respects Discord's message size limits."""
    try:
        picture=await asyncio.to_thread(cards.profile_card,name,city,resource,total,review=review)
        embed=discord.Embed(colour=discord.Colour.from_rgb(114,184,218))
        embed.set_image(url="attachment://profile.png")
        await interaction.followup.send(content=text,embed=embed,
            file=_asset(picture,"profile.png",f"Profile for {cards.clean(name)} of {cards.clean(city)}; {total} points"),
            ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
    except (discord.HTTPException,OSError,ValueError,MemoryError) as exc:
        log.warning("Profile image unavailable; sending text: %s",exc)
        await interaction.followup.send(content=text,ephemeral=True,
                                        allowed_mentions=discord.AllowedMentions.none())


async def send_champions(interaction, text, players, cities, *, final: bool):
    try:
        image=await asyncio.to_thread(cards.champions_card, players, cities, final=final)
        embed=discord.Embed(colour=discord.Colour.gold())
        embed.set_image(url="attachment://champions.png")
        await interaction.followup.send(content=text,embed=embed,
            file=_asset(image,"champions.png","Top three individual players and honorary leading city"),
            ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
    except (discord.HTTPException,OSError,ValueError,MemoryError) as exc:
        log.warning("Champions image unavailable; sending text: %s",exc)
        await interaction.followup.send(content=text,ephemeral=True,
                                        allowed_mentions=discord.AllowedMentions.none())


async def send_world_status(interaction, text, state, view):
    """Slash-command world card with mobile-readable plain text and controls."""
    try:
        picture=await asyncio.to_thread(cards.world_status_card,state)
        embed=discord.Embed(colour=discord.Colour.from_rgb(114,184,218))
        embed.set_image(url="attachment://world.png")
        await interaction.followup.send(content=text,embed=embed,
            file=_asset(picture,"world.png","Daily Snow Don and city fortress HP and attempts"),
            view=view,ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
    except (discord.HTTPException,OSError,ValueError,MemoryError) as exc:
        log.warning("World card unavailable; using full text: %s",exc)
        await interaction.followup.send(content=text,view=view,ephemeral=True,
                                        allowed_mentions=discord.AllowedMentions.none())
