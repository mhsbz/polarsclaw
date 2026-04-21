"""Unified runtime dispatch for CLI, gateway, daemon, and cron paths."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Awaitable, Callable

from polarsclaw.errors import RecordNotFoundError
from polarsclaw.skills.executor import execute_skill
from polarsclaw.types import DMScope

if TYPE_CHECKING:
    from polarsclaw.agents.loop import AgentLoop
    from polarsclaw.app import AppContext
    from polarsclaw.skills.parser import SkillEntry
    from polarsclaw.sessions.models import Session

logger = logging.getLogger(__name__)

TokenCallback = Callable[[str], Awaitable[None]]


@dataclass(slots=True)
class DispatchResult:
    """Final result from dispatching one message through the runtime."""

    session: Session
    agent_id: str
    response: str
    skill: SkillEntry | None = None


def resolve_dm_scope(raw_scope: str) -> DMScope:
    """Parse the configured DM scope, defaulting to MAIN."""
    try:
        return DMScope(raw_scope)
    except ValueError:
        logger.warning("Unknown dm_scope=%s; defaulting to main", raw_scope)
        return DMScope.MAIN


def resolve_routed_agent(
    ctx: AppContext,
    *,
    peer_id: str | None = None,
    channel_id: str | None = None,
    roles: list[str] | None = None,
    account_id: str | None = None,
) -> tuple[str, AgentLoop]:
    """Resolve the runtime agent using router-first semantics with fallback."""
    agent_id = ctx.router.resolve_agent_id(
        peer_id=peer_id,
        channel_id=channel_id,
        roles=roles,
        account_id=account_id,
    )
    return agent_id, ctx.agents[agent_id]


def build_agent_factory(
    ctx: AppContext,
    *,
    peer_id: str | None = None,
    channel_id: str | None = None,
    roles: list[str] | None = None,
    account_id: str | None = None,
) -> Callable[[], Awaitable[AgentLoop]]:
    """Build a reusable factory that resolves the current runtime agent."""

    async def _factory() -> AgentLoop:
        _, agent = resolve_routed_agent(
            ctx,
            peer_id=peer_id,
            channel_id=channel_id,
            roles=roles,
            account_id=account_id,
        )
        return agent

    return _factory


async def dispatch_message(
    ctx: AppContext,
    *,
    content: str,
    session_id: str | None = None,
    peer_id: str | None = None,
    channel_id: str | None = None,
    roles: list[str] | None = None,
    account_id: str | None = None,
    on_token: TokenCallback | None = None,
    allow_skill: bool = True,
) -> DispatchResult:
    """Persist, route, execute, and persist one logical user message."""
    agent_id, agent = resolve_routed_agent(
        ctx,
        peer_id=peer_id,
        channel_id=channel_id,
        roles=roles,
        account_id=account_id,
    )

    if session_id is not None:
        try:
            session = await ctx.session_manager.resume(session_id)
        except RecordNotFoundError:
            session = await ctx.session_manager.create_with_id(
                session_id,
                agent_id,
                peer_id=peer_id,
                channel_id=channel_id,
            )
    else:
        session = await ctx.session_manager.resolve(
            agent_id,
            peer_id=peer_id,
            channel_id=channel_id,
        )

    await ctx.message_repo.add(session.id, "user", content)

    skill = ctx.skill_registry.match(content) if allow_skill else None
    if skill is not None:
        try:
            response = await execute_skill(
                skill=skill,
                message=content,
                agent_loop=agent,
                settings=ctx.settings,
            )
        except Exception:
            logger.warning("Skill %s failed; falling back to normal agent", skill.name, exc_info=True)
            skill = None
            response = await agent.run(content, session_id=session.id, on_token=on_token)
        else:
            if on_token is not None and response:
                await on_token(response)
    else:
        response = await agent.run(content, session_id=session.id, on_token=on_token)

    await ctx.message_repo.add(
        session.id,
        "assistant",
        response,
        metadata={"agent_id": agent_id, "skill": skill.name if skill else None},
    )

    return DispatchResult(
        session=session,
        agent_id=agent_id,
        response=response,
        skill=skill,
    )
