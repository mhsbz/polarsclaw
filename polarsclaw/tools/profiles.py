"""Tool profiles for different use cases."""

from __future__ import annotations

# Profile -> list of groups to include
PROFILES: dict[str, list[str]] = {
    "full": [
        "group:memory", "group:cron", "group:session",
        "group:skill", "group:fs", "group:runtime",
    ],
    "coding": [
        "group:memory", "group:fs", "group:runtime",
    ],
    "minimal": [
        "group:memory",
    ],
}


def get_profile_groups(profile_name: str) -> list[str]:
    """Return the list of group names for a profile, defaulting to 'full'."""
    return PROFILES.get(profile_name, PROFILES["full"])
