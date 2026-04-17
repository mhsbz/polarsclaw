"""Tests for polarsclaw.routing."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from polarsclaw.errors import RoutingError
from polarsclaw.routing.bindings import Binding, compute_priority, resolve_bindings
from polarsclaw.routing.router import MultiAgentRouter


class TestComputePriority:
    def test_peer_highest(self) -> None:
        b = Binding(agent_id="a", peer_id="p1")
        assert b.priority == 8

    def test_channel(self) -> None:
        b = Binding(agent_id="a", channel_id="c1")
        assert b.priority == 4

    def test_account(self) -> None:
        b = Binding(agent_id="a", account_id="acc")
        assert b.priority == 1

    def test_combined(self) -> None:
        b = Binding(agent_id="a", peer_id="p1", channel_id="c1")
        assert b.priority == 12

    def test_empty(self) -> None:
        b = Binding(agent_id="a")
        assert b.priority == 0


class TestResolveBindings:
    def test_most_specific_wins(self) -> None:
        bindings = [
            Binding(agent_id="general", account_id="acc1"),
            Binding(agent_id="specific", peer_id="p1", account_id="acc1"),
        ]
        result = resolve_bindings(bindings, peer_id="p1", account_id="acc1")
        assert result == "specific"

    def test_no_match(self) -> None:
        bindings = [Binding(agent_id="a", peer_id="p1")]
        assert resolve_bindings(bindings, peer_id="p2") is None

    def test_role_subset(self) -> None:
        bindings = [Binding(agent_id="admin-agent", roles=["admin"])]
        result = resolve_bindings(bindings, roles=["admin", "user"])
        assert result == "admin-agent"

    def test_role_mismatch(self) -> None:
        bindings = [Binding(agent_id="admin-agent", roles=["admin"])]
        assert resolve_bindings(bindings, roles=["user"]) is None


class TestMultiAgentRouter:
    def _mock_agent(self, name: str):
        agent = MagicMock()
        agent.name = name
        return agent

    def test_resolve_to_correct_agent(self) -> None:
        agents = {"a1": self._mock_agent("a1"), "a2": self._mock_agent("a2")}
        bindings = [Binding(agent_id="a1", peer_id="alice")]
        router = MultiAgentRouter(agents, bindings)
        result = router.resolve(peer_id="alice")
        assert result is agents["a1"]

    def test_default_fallback(self) -> None:
        agents = {"default": self._mock_agent("default")}
        router = MultiAgentRouter(agents, [], default_agent="default")
        result = router.resolve(peer_id="anyone")
        assert result is agents["default"]

    def test_no_match_no_default_raises(self) -> None:
        agents = {"a1": self._mock_agent("a1")}
        router = MultiAgentRouter(agents, [], default_agent=None)
        with pytest.raises(RoutingError):
            router.resolve(peer_id="unknown")

    def test_resolved_agent_not_registered_raises(self) -> None:
        agents = {"a1": self._mock_agent("a1")}
        bindings = [Binding(agent_id="missing", peer_id="alice")]
        router = MultiAgentRouter(agents, bindings)
        with pytest.raises(RoutingError, match="not registered"):
            router.resolve(peer_id="alice")
