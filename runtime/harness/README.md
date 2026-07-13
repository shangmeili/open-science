# HEOR research-agent harness

A single research execution agent supervised through explicit human approval
gates. It delivers work, reviews itself, and revises itself, while humans retain
decision authority and independent validation remains external to the agent.

## Core Idea

After each work cycle, ask: what could be better? Save reusable lessons into
memory and promote repeatedly verified lessons into principles. Self-improvement
may change working tactics, but it cannot weaken data boundaries, approval gates,
or evidence requirements.

## Repository Layout

| Path | Purpose |
| --- | --- |
| `AGENTS.md` | Rule core: identity, mission, principles, and self-evolution loop. |
| `KNOWLEDGE.md` | Knowledge index. |
| `knowledge/` | Current facts: `system.md` covers the system model, and `current-state.md` covers goals and progress. |
| `notes/` | Daily logs appended by date. Old entries are not edited after their day ends. |

## Startup Order

1. Read `AGENTS.md`.
2. Read `KNOWLEDGE.md`.
3. Read the latest 2-3 files in `notes/`.
4. Check the goal, worktree, code, data, and logs.

## Memory Rules

- `knowledge/` stores current facts only; update it when facts change.
- `notes/` stores daily logs; append during the day and do not edit old entries.
- Principle changes go directly into `AGENTS.md`.
