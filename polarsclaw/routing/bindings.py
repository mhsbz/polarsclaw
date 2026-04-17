"""Binding model and most-specific-wins resolution algorithm."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class Binding(BaseModel):
    """Maps a context (peer, channel, role, account) to an agent."""

    agent_id: str
    peer_id: str | None = None
    channel_id: str | None = None
    roles: list[str] | None = None
    account_id: str | None = None
    priority: int = Field(default=0, description="Auto-computed; higher = more specific.")

    @model_validator(mode="after")
    def _auto_priority(self) -> Binding:
        self.priority = compute_priority(self)
        return self


def compute_priority(binding: Binding) -> int:
    """Score a binding by specificity: more specific fields = higher priority.

    Weights (cumulative):
      peer_id    +8   (most specific)
      channel_id +4
      roles      +2
      account_id +1
    """
    score = 0
    if binding.peer_id is not None:
        score += 8
    if binding.channel_id is not None:
        score += 4
    if binding.roles:
        score += 2
    if binding.account_id is not None:
        score += 1
    return score


def resolve_bindings(
    bindings: list[Binding],
    *,
    peer_id: str | None = None,
    channel_id: str | None = None,
    roles: list[str] | None = None,
    account_id: str | None = None,
) -> str | None:
    """Return the ``agent_id`` of the most-specific matching binding.

    A binding *matches* if every non-None field on the binding equals (or is a
    subset of, for roles) the corresponding lookup value.  Among all matches
    the one with the highest priority wins.  Returns ``None`` when nothing
    matches.
    """
    best_agent: str | None = None
    best_priority = -1

    for b in bindings:
        if b.peer_id is not None and b.peer_id != peer_id:
            continue
        if b.channel_id is not None and b.channel_id != channel_id:
            continue
        if b.roles:
            if not roles or not set(b.roles).issubset(set(roles)):
                continue
        if b.account_id is not None and b.account_id != account_id:
            continue

        if b.priority > best_priority:
            best_priority = b.priority
            best_agent = b.agent_id

    return best_agent
