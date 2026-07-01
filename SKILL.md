---
name: codex-mcp-localize
description: Localize, pin, audit, and update Codex MCP servers declared in config.toml. Use when Codex needs to move MCP startup from npx or uvx cold starts to local fixed installs, compare installed MCP versions with remote versions, collect official release/change notes, ask the user which MCPs to update, install selected updates, or generate safe config.toml rewrite suggestions for local MCP executables.
---

# Codex MCP Localize

Use this skill to manage MCP servers from a Codex `config.toml` without relying on slow `npx ...@latest` or `uvx ...` cold starts during every new session.

## Core Rules

- Treat `config.toml` as the source of truth for configured MCP servers.
- Install into a Codex-owned tool area, not system-wide package locations:
  - npm MCP packages: `%USERPROFILE%\.codex\mcp-tools\npm`
  - uv tool MCP packages: uv's tool environment, tracked in `%USERPROFILE%\.codex\mcp-tools\mcp-localize-state.json`
- Do not update packages automatically after an audit. Present the version and change report, then ask the user which MCPs to update.
- Prefer official change sources:
  1. GitHub releases from package metadata
  2. npm or PyPI package metadata and publish dates
  3. linked changelog/repository URLs for manual follow-up
- Be explicit when official release notes cannot be found. Do not invent feature changes.
- Rewrite `config.toml` only for the initial migration to local fixed executables, or when the user adds/removes/renames MCP servers, changes command-line arguments, or a package changes its executable entrypoint.
- Back up `config.toml` before any rewrite.

## Workflow

1. Run an offline audit first. This verifies parsing and migration status without
   touching npm, PyPI, or GitHub:

   ```powershell
   uv run "<skill-dir>\scripts\codex_mcp_localize.py" audit --offline
   ```

2. Run a remote audit when version and release-note details are needed:

   ```powershell
   uv run "<skill-dir>\scripts\codex_mcp_localize.py" audit --release-notes --out "$env:USERPROFILE\.codex\mcp-tools\reports\mcp-audit.md"
   ```

3. Read the report. It should include:
   - server name
   - package manager (`npm` or `uv`)
   - package name
   - requested version from config
   - local installed version
   - remote latest version
   - update status
   - official release/change-note findings when available
   - whether `config.toml` still needs migration

4. Ask the user which MCPs to install or update. If the user says none, stop.

5. Install only the selected MCPs:

   ```powershell
   uv run "<skill-dir>\scripts\codex_mcp_localize.py" install --servers Playwright context7
   ```

6. For first-time migration, generate config snippets:

   ```powershell
   uv run "<skill-dir>\scripts\codex_mcp_localize.py" config-snippets --servers Playwright context7
   ```

7. Ask before editing `config.toml`. If approved, back it up and apply only the relevant MCP stanza changes. Preserve existing env sections such as `[mcp_servers.exa.env]`.

8. Run another audit to verify:

   ```powershell
   uv run "<skill-dir>\scripts\codex_mcp_localize.py" audit --release-notes
   ```

## Config Rewrite Policy

After first-time localization, future version updates normally do not require `config.toml` changes. The config points to a stable local executable path; updating the package changes the installed files behind that path.

Rewrite config again only when:

- the user adds a new MCP server that still uses `npx` or `uvx`;
- the user changes startup args or env requirements;
- a package changes its CLI executable name;
- the local tool root is moved;
- a server is intentionally removed or renamed.

## Release-Diff Expectations

For every update candidate, collect as much official change detail as practical:

- new features or MCP tools added;
- removed or deprecated behavior;
- breaking changes or migration notes;
- dependency/runtime changes that affect startup;
- security fixes when explicitly documented.

If structured release notes are unavailable, say that and provide the official package/repository links instead of guessing.

See `references/version-diff-policy.md` for the detailed evidence policy.
