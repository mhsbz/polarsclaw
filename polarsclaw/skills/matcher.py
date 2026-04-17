"""Trigger matching — keyword / substring scoring."""

from __future__ import annotations


def match_triggers(
    message: str,
    triggers: list[str],
    threshold: float = 0.7,
) -> float:
    """Return a match score (0.0–1.0) for *message* against *triggers*.

    Scoring rules (highest wins):
    - Exact match (trigger == message, case-insensitive): **1.0**
    - Trigger is a substring of message: **0.8**
    - Partial word overlap ≥ 50 %: **0.5–0.7** (proportional)
    """
    if not triggers:
        return 0.0

    msg_lower = message.lower().strip()
    msg_words = set(msg_lower.split())
    best = 0.0

    for trigger in triggers:
        trig_lower = trigger.lower().strip()
        if not trig_lower:
            continue

        # Exact match
        if trig_lower == msg_lower:
            return 1.0

        # Substring match
        if trig_lower in msg_lower:
            best = max(best, 0.8)
            continue

        # Word-overlap scoring
        trig_words = set(trig_lower.split())
        if not trig_words:
            continue
        overlap = len(trig_words & msg_words)
        ratio = overlap / len(trig_words)
        if ratio >= 0.5:
            # Map 0.5–1.0 ratio → 0.5–0.7 score
            score = 0.5 + 0.2 * ((ratio - 0.5) / 0.5)
            best = max(best, score)

    return best
