"""Discord access guard shared by slash commands, buttons and modal submissions.

Discord invokes a View/Modal directly, without passing through the
CommandTree.interaction_check hook. All canonical game surfaces must therefore
revalidate the *current* linked identity, not trust the owner of an old menu.
"""
from __future__ import annotations

import asyncio
import logging

from snowfall.platform.identity import IdentityError

log = logging.getLogger(__name__)

UNLINKED_MESSAGE = (
    "🔗 Link Discord to your Underworld character before playing. "
    "Open Snowfall Web, sign in through Underworld and choose Link Discord account."
)
UNAVAILABLE_MESSAGE = (
    "⚠️ Shared game identity is temporarily unavailable. "
    "No game action was performed. Please retry shortly."
)


async def check_linked_player(interaction) -> bool:
    """Enforce a fresh canonical link on every Discord interaction surface.

    A non-shared historical worker has no unified_identity and retains its
    original behaviour. Fail closed on transient PostgreSQL issues, without
    disclosing DB connection details or session tokens to Discord users.
    """
    identities = getattr(interaction.client, "unified_identity", None)
    if identities is None:
        return True
    try:
        await asyncio.to_thread(
            identities.principal_for_discord, str(interaction.user.id))
    except IdentityError:
        await interaction.response.send_message(UNLINKED_MESSAGE, ephemeral=True)
        return False
    except Exception:
        log.exception("Shared Discord identity lookup failed; blocking action")
        await interaction.response.send_message(UNAVAILABLE_MESSAGE, ephemeral=True)
        return False
    return True


def shared_qa(client) -> bool:
    """Whether this exact worker currently uses the canonical QA adapter."""
    return bool(getattr(getattr(client, "store", None), "unified_discord", False))
