# Codex MCP Localize

English | [简体中文](README.zh-CN.md)

`codex-mcp-localize` is a Codex skill and helper script for auditing, pinning, and updating MCP servers declared in Codex `config.toml`.

It is useful when your Codex setup starts MCP servers through slow cold-start commands such as `npx ...@latest` or `uvx ...`. The workflow helps move those servers to local, fixed installations, then reports when updates are available.

## What It Does

Codex MCP servers are often configured with commands such as:

```toml
[mcp_servers.context7]
type = "stdio"
command = "npx"
args = ["-y", "@upstash/context7-mcp@latest"]
```

That is convenient, but it can add package resolution, download, and cold-start latency to every new Codex session. `codex-mcp-localize` helps you replace those transient startup commands with local, pinned installations.

The tool can:

- Inspect MCP servers declared in Codex `config.toml`.
- Detect `npx` and `uvx` based MCP packages.
- Compare requested, installed, and remote latest versions.
- Install selected MCP packages locally.
- Generate suggested local `config.toml` stanzas.
- Produce Markdown or JSON audit reports.
- Collect official release notes where available.

## Repository Layout

```text
.
├── SKILL.md
├── README.md
├── README.zh-CN.md
├── agents/
│   └── openai.yaml
├── references/
│   └── version-diff-policy.md
└── scripts/
    └── codex_mcp_localize.py
```

## Install as a Codex Skill

Clone this repository into your Codex skills directory:

```powershell
git clone https://github.com/soberw/codex-mcp-localize.git $env:USERPROFILE\.codex\skills\codex-mcp-localize
```

You can then invoke it as a Codex skill, or run the helper script directly:

```powershell
uv run "$env:USERPROFILE\.codex\skills\codex-mcp-localize\scripts\codex_mcp_localize.py" audit --offline
```

## Commands

Offline audit:

```powershell
uv run "$env:USERPROFILE\.codex\skills\codex-mcp-localize\scripts\codex_mcp_localize.py" audit --offline
```

Remote audit with release notes:

```powershell
uv run "$env:USERPROFILE\.codex\skills\codex-mcp-localize\scripts\codex_mcp_localize.py" audit --release-notes --out "$env:USERPROFILE\.codex\mcp-tools\reports\mcp-audit.md"
```

Audit selected servers:

```powershell
uv run "$env:USERPROFILE\.codex\skills\codex-mcp-localize\scripts\codex_mcp_localize.py" audit --offline --servers context7 Playwright
```

Install or update selected servers:

```powershell
uv run "$env:USERPROFILE\.codex\skills\codex-mcp-localize\scripts\codex_mcp_localize.py" install --servers context7 Playwright
```

Generate suggested local config snippets:

```powershell
uv run "$env:USERPROFILE\.codex\skills\codex-mcp-localize\scripts\codex_mcp_localize.py" config-snippets --servers context7 Playwright
```

## Defaults

- Config file: `%USERPROFILE%\.codex\config.toml`
- Tool root: `%USERPROFILE%\.codex\mcp-tools`
- npm package root: `%USERPROFILE%\.codex\mcp-tools\npm`
- State file: `%USERPROFILE%\.codex\mcp-tools\mcp-localize-state.json`
- Report directory: `%USERPROFILE%\.codex\mcp-tools\reports`

Override them with global options:

```powershell
uv run "scripts\codex_mcp_localize.py" --config "C:\path\to\config.toml" --root "C:\path\to\mcp-tools" audit --offline
```

## Safety Model

- The script does not modify `config.toml` automatically.
- Back up `config.toml` before applying generated snippets.
- After first-time localization, normal package updates usually do not require another config rewrite.
- Release-note reporting prefers official GitHub releases, official changelogs, and npm/PyPI metadata. If structured release notes are unavailable, the report says so instead of guessing.

## Recommended Workflow

1. Run `audit --offline` to verify local config parsing.
2. Run `audit --release-notes` to review remote versions and official changes.
3. Decide which MCP servers should be installed or updated.
4. Run `install --servers ...` only for the selected servers.
5. Run `config-snippets --servers ...` for first-time migration.
6. Back up and edit `config.toml` manually.
7. Run another audit to verify the result.

