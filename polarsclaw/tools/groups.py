"""Built-in tool group definitions."""

from __future__ import annotations

# Group name -> list of tool names that belong to this group
BUILTIN_GROUPS: dict[str, list[str]] = {
    "group:memory": ["save_memory", "recall_memory", "list_memories"],
    "group:cron": ["create_cron", "list_crons", "delete_cron", "cron_history"],
    "group:session": ["switch_session", "list_sessions"],
    "group:skill": ["list_skills", "invoke_skill"],
    "group:fs": [],       # populated by DeepAgents built-in tools
    "group:runtime": [],  # populated by DeepAgents built-in tools
}


def get_builtin_groups() -> dict[str, list[str]]:
    """Return a copy of the built-in group definitions."""
    return dict(BUILTIN_GROUPS)
