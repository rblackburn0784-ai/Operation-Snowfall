"""Consistent account-link checks for every Discord interaction surface.

Slash command tree checks do not guard Discord UI component callbacks or
modal submissions. A previously opened menu can survive across account
unlinking/retirement, and public buttons can be clicked by anyone. Shared QA
therefore checks the authenticated Discord identity before every interaction
that could lead to a gameplay read or write, not just before slash commands.
The original SQLite-only bot remains unchanged when unified_identity is None.
"""
from __future__ import annotations

import asyncio
import logging

from snowfall.platform.identity import IdentityError

log = logging.getLogger(__name__)


async def require_linked_discord(interaction) -> bool:
    """Fail closed for shared-game QA and respond privately without leaking IDs.

    Uses the interaction's trusted Discord actor, NEVER a user-supplied account
    or profile ID. For the original pre-shared game no identity repository is
    configured, and the existing interaction rules remain unchanged.
    """
    identity = getattr(interaction.client, "unified_identity", None)
    if identity is None:
        return True
    try:
        principal = await asyncio.to_thread(
            identity.principal_for_discord, str(interaction.user.id))
        links = await asyncio.to_thread(identity.links, principal)
        if not any(link["provider"] == "underworld" for link in links):
            raise IdentityError("Discord is not linked to an Underworld character")
    except IdentityError:
        message = ("🔗 Link your Discord login to your Underworld character "
                   "on Snowfall Web before playing. Try `/snowbridge link`.")
    except Exception:
        # Database outages must not silently create a second, Discord-only
        # profile through an old menu. Avoid logging tokens/DSN.
        log.warning("Shared Discord identity lookup failed; blocking old menu", exc_info=False)
        message = ("⚠️ Shared account verification is temporarily unavailable. "
                   "No game action was performed; please try again.")
    else:
        return True
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)
    return False
