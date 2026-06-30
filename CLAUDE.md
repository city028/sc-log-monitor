# sc-log-monitor

---

VAULT_PROJECT_NAME: sc-log-monitor

## Project Overview
<!-- Describe the project here -->

---

## Rules

1. Think before coding: Before implementing any solution, explicitly state your assumptions, clarify any confusion immediately, and openly present all tradeoffs and simpler alternatives rather than deciding in silence
2. Simplicity first: Write the absolute minimum code necessary to solve the exact problem requested, strictly avoiding unrequested features, premature abstractions, or unnecessary complexity
3. Surgical changes: When editing existing code, alter only what is strictly necessary to fulfill the request, matching the established style and removing only the unused code created by your own changes
4. Goal-Driven Execution: Transform tasks into clear, verifiable goals with explicit success criteria so you can independently execute and iterate through a planned loop until all tests pass

---

## Context

Read `AGENTS.md` from the vault root via the vault MCP (path: `AGENTS.md`) at the start
of every session — it defines how to navigate the vault, the LOD principle for loading
context without flooding the context window, cross-linking philosophy, and how to find
project and research information efficiently.

---

## Vault Sync

To push files to the vault, run:
```bash
vault-push
```
- Do NOT use vault:write_files or vault MCP tools directly for pushing
- vault-push auto-discovers LESSONS-LEARNED.md, NOTES.md, README.md, TODO.md in cwd
- To push specific files: vault-push NOTES.md LESSONS-LEARNED.md
- For reading vault context, use vault MCP tools freely

---


## Stack
<!-- Languages, frameworks, key dependencies -->

---

## Architecture
<!-- High-level structure and component overview -->

---

## Conventions

- Always make a backup of any file before editing it — copy to a `.bak` or timestamped filename in the bak directory in the root
- Keep handlers thin — business logic goes in testable helper functions, not in entry points or command handlers.
- All Claude-managed vault files use `UPPERCASE-NAME.md` naming (e.g. `NOTES.md`, `TODO.md`).
- Never use merged cells or filler rows in Excel/spreadsheet output.
- Before building any merged dataset from multiple sources, audit ALL sources first to identify the full column superset.

---

## Key Files
<!-- List important files and their purpose -->

---

## Vault
- Vault project note: `development/Projects/sc-log-monitor/NOTES.md`

---

## TODO
<!-- Running list of tasks — keep this in sync with TODO.md if present -->

---

## Notes
<!-- Anything else Claude should keep in mind for this project -->
