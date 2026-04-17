# PolarsClaw

A local-first, single-user personal AI assistant — OpenClaw-inspired, built on LangChain DeepAgents.

## Features

- **12 Core Subsystems**: Gateway, Agent Loop, Multi-Agent Routing, Tool System, Skills, Cron/Scheduling, Context Engine, Command Queue, Memory, Sessions, Plugins, CLI+Daemon
- **MiniMax Integration**: Uses MiniMax M2.7 via Anthropic-compatible API, auto-loads credentials from OpenClaw
- **DeepAgents-First**: Leverages DeepAgents for sub-agents, filesystem, summarization, checkpointing
- **Local-First**: SQLite + FTS5 for storage, no external services required

## Quick Start

```bash
pip install -e .
polarsclaw chat
```

## Commands

```
polarsclaw chat [--session ID]    # Interactive chat
polarsclaw message TEXT            # Single message
polarsclaw skills list             # List skills
polarsclaw cron list               # List cron jobs
polarsclaw daemon start|stop|status
polarsclaw config show|set KEY VALUE
```

## Configuration

Config at `~/.polarsclaw/config.json`. Auto-loads MiniMax provider from OpenClaw (`~/.openclaw/`).

## Testing

```bash
pip install -e ".[dev]"
pytest tests/ -v
```
