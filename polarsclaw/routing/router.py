"""MultiAgentRouter — resolve incoming context to the correct AgentLoop."""

from __future__ import annotations

from typing import TYPE_CHECKING

from polarsclaw.errors import RoutingError
from polarsclaw.routing.bindings import Binding, resolve_bindings

if TYPE_CHECKING:
    from polarsclaw.agents.loop import AgentLoop


class MultiAgentRouter:
    """Route messages to agents based on binding resolution.

    Parameters
    ----------
    agents:
        Mapping of ``agent_id`` to an initialised :class:`AgentLoop`.
    bindings:
        Ordered list of :class:`Binding` rules.
    default_agent:
        Fallback ``agent_id`` used when no binding matches.  Set to ``""``
        or ``None`` to disable the fallback (a :class:`RoutingError` will be
        raised instead).
    """

    def __init__(
        self,
        agents: dict[str, AgentLoop],
        bindings: list[Binding],
        default_agent: str | None = None,
    ) -> None:
        self._agents = agents
        self._bindings = bindings
        self._default_agent = default_agent

    def resolve(
        self,
        *,
        peer_id: str | None = None,
        channel_id: str | None = None,
        roles: list[str] | None = None,
        account_id: str | None = None,
    ) -> AgentLoop:
        """Resolve context to an :class:`AgentLoop`.

        Raises
        ------
        RoutingError
            If no binding matches and no default agent is configured, or if
            the resolved ``agent_id`` is not present in the agents dict.
        """
        agent_id = self.resolve_agent_id(
            peer_id=peer_id,
            channel_id=channel_id,
            roles=roles,
            account_id=account_id,
        )

        return self._agents[agent_id]

    def resolve_agent_id(
        self,
        *,
        peer_id: str | None = None,
        channel_id: str | None = None,
        roles: list[str] | None = None,
        account_id: str | None = None,
    ) -> str:
        """Resolve context to an agent id, applying fallback policy."""
        agent_id = resolve_bindings(
            self._bindings,
            peer_id=peer_id,
            channel_id=channel_id,
            roles=roles,
            account_id=account_id,
        )

        if agent_id is None:
            if self._default_agent and self._default_agent in self._agents:
                return self._default_agent
            raise RoutingError(
                f"No binding matched (peer={peer_id}, channel={channel_id}, "
                f"roles={roles}, account={account_id}) and no default agent configured"
            )

        if agent_id not in self._agents:
            raise RoutingError(
                f"Binding resolved to agent '{agent_id}' which is not registered"
            )

        return agent_id
