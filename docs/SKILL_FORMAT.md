# PolarsClaw Skill Format

## Overview

Skills are Markdown files that describe capabilities PolarsClaw can use. Place `.md` files in the skills directory (`~/.polarsclaw/skills/`) and they'll be auto-discovered.

## Format

```markdown
---
name: my_skill
description: What this skill does
triggers:
  - "keyword1"
  - "keyword2"
---

## Instructions

Detailed instructions for the AI when executing this skill...

## Parameters

- param1: Description
- param2: Description
```

## Required Fields

- `name` (string): Unique skill identifier
- `description` (string): Brief description shown in skill listings

## Optional Fields

- `triggers` (list of strings): Keywords that auto-activate this skill

## Body

Everything after the YAML frontmatter is the skill's instruction body. This becomes the system prompt for the sub-agent that executes the skill.

## Example

See `polarsclaw/skills/example.md` for a working translation skill.
