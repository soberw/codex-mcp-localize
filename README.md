# Codex MCP Localize

`codex-mcp-localize` is a Codex skill and helper script for auditing, pinning, and updating MCP servers declared in Codex `config.toml`.

It is useful when your Codex setup starts MCP servers through slow cold-start commands such as `npx ...@latest` or `uvx ...`. The workflow helps move those servers to local, fixed installations, then reports when updates are available.

## 中文说明

### 这个项目解决什么问题

Codex 的 `config.toml` 里经常会用类似下面的方式启动 MCP：

```toml
[mcp_servers.context7]
type = "stdio"
command = "npx"
args = ["-y", "@upstash/context7-mcp@latest"]
```

这种写法简单，但每次新会话都可能触发包解析、下载或冷启动，尤其在 Windows 上会明显拖慢启动。`codex-mcp-localize` 的目标是：

- 扫描 Codex `config.toml` 中通过 `npx` / `uvx` 启动的 MCP server。
- 识别对应的 npm / PyPI 包和版本。
- 把 MCP 安装到本地固定位置。
- 生成建议的 `config.toml` 本地启动配置。
- 后续审计本地版本和远端最新版本，输出更新报告。
- 尽量收集官方 release notes / changelog，不猜测更新内容。

### 文件结构

```text
.
├── SKILL.md
├── README.md
├── agents/
│   └── openai.yaml
├── references/
│   └── version-diff-policy.md
└── scripts/
    └── codex_mcp_localize.py
```

### 安装为 Codex skill

把本仓库放到 Codex skills 目录下，例如：

```powershell
git clone https://github.com/soberw/codex-mcp-localize.git $env:USERPROFILE\.codex\skills\codex-mcp-localize
```

之后在 Codex 中即可使用这个 skill。也可以直接运行脚本：

```powershell
uv run "$env:USERPROFILE\.codex\skills\codex-mcp-localize\scripts\codex_mcp_localize.py" audit --offline
```

### 常用命令

先做离线审计，只解析本机配置，不访问 npm / PyPI / GitHub：

```powershell
uv run "$env:USERPROFILE\.codex\skills\codex-mcp-localize\scripts\codex_mcp_localize.py" audit --offline
```

生成带版本和 release notes 的审计报告：

```powershell
uv run "$env:USERPROFILE\.codex\skills\codex-mcp-localize\scripts\codex_mcp_localize.py" audit --release-notes --out "$env:USERPROFILE\.codex\mcp-tools\reports\mcp-audit.md"
```

只审计指定 MCP server：

```powershell
uv run "$env:USERPROFILE\.codex\skills\codex-mcp-localize\scripts\codex_mcp_localize.py" audit --offline --servers context7 Playwright
```

安装或更新指定 server 的本地固定版本：

```powershell
uv run "$env:USERPROFILE\.codex\skills\codex-mcp-localize\scripts\codex_mcp_localize.py" install --servers context7 Playwright
```

生成建议写入 `config.toml` 的本地 MCP 配置片段：

```powershell
uv run "$env:USERPROFILE\.codex\skills\codex-mcp-localize\scripts\codex_mcp_localize.py" config-snippets --servers context7 Playwright
```

### 默认路径

- Codex 配置：`%USERPROFILE%\.codex\config.toml`
- MCP 本地工具根目录：`%USERPROFILE%\.codex\mcp-tools`
- npm MCP 包目录：`%USERPROFILE%\.codex\mcp-tools\npm`
- 状态文件：`%USERPROFILE%\.codex\mcp-tools\mcp-localize-state.json`
- 报告目录：`%USERPROFILE%\.codex\mcp-tools\reports`

这些路径可以通过脚本参数覆盖：

```powershell
uv run "scripts\codex_mcp_localize.py" --config "C:\path\to\config.toml" --root "C:\path\to\mcp-tools" audit --offline
```

### 安全边界

- 脚本不会自动修改 `config.toml`。
- 首次迁移时应先备份 `config.toml`，再人工应用 `config-snippets` 输出。
- 后续版本更新通常不需要再改 `config.toml`，因为配置已经指向稳定的本地可执行文件。
- release notes 只优先使用官方 GitHub releases、官方 changelog、npm/PyPI 元数据；找不到结构化说明时会明确说明，不会编造变更。

### 推荐工作流

1. `audit --offline`：确认脚本能正确解析当前配置。
2. `audit --release-notes`：查看远端版本和官方变更信息。
3. 人工决定要安装或更新哪些 MCP。
4. `install --servers ...`：只安装选中的 MCP。
5. `config-snippets --servers ...`：首次迁移时生成本地配置片段。
6. 手动备份并修改 `config.toml`。
7. 再次运行 `audit --release-notes` 验证状态。

## English

### What this project does

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

### Install as a Codex skill

Clone this repository into your Codex skills directory:

```powershell
git clone https://github.com/soberw/codex-mcp-localize.git $env:USERPROFILE\.codex\skills\codex-mcp-localize
```

You can then invoke it as a Codex skill, or run the helper script directly:

```powershell
uv run "$env:USERPROFILE\.codex\skills\codex-mcp-localize\scripts\codex_mcp_localize.py" audit --offline
```

### Commands

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

### Defaults

- Config file: `%USERPROFILE%\.codex\config.toml`
- Tool root: `%USERPROFILE%\.codex\mcp-tools`
- npm package root: `%USERPROFILE%\.codex\mcp-tools\npm`
- State file: `%USERPROFILE%\.codex\mcp-tools\mcp-localize-state.json`
- Report directory: `%USERPROFILE%\.codex\mcp-tools\reports`

Override them with global options:

```powershell
uv run "scripts\codex_mcp_localize.py" --config "C:\path\to\config.toml" --root "C:\path\to\mcp-tools" audit --offline
```

### Safety model

- The script does not modify `config.toml` automatically.
- Back up `config.toml` before applying generated snippets.
- After first-time localization, normal package updates usually do not require another config rewrite.
- Release-note reporting prefers official GitHub releases, official changelogs, and npm/PyPI metadata. If structured release notes are unavailable, the report says so instead of guessing.

### Recommended workflow

1. Run `audit --offline` to verify local config parsing.
2. Run `audit --release-notes` to review remote versions and official changes.
3. Decide which MCP servers should be installed or updated.
4. Run `install --servers ...` only for the selected servers.
5. Run `config-snippets --servers ...` for first-time migration.
6. Back up and edit `config.toml` manually.
7. Run another audit to verify the result.

