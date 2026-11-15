"""Pure dedicated-guild and host/staff permission checks."""
from __future__ import annotations


def permitted_guild(interaction_guild_id: int | None, configured_guild_id: int) -> bool:
    return interaction_guild_id is not None and interaction_guild_id == configured_guild_id


def is_host(user_id: int, hosts: frozenset[int]) -> bool:
    return user_id in hosts


def is_staff(user_id: int, hosts: frozenset[int], staff_roles: frozenset[int],
             user_roles: frozenset[int]) -> bool:
    return is_host(user_id, hosts) or bool(staff_roles.intersection(user_roles))
