from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = Path.home() / ".codex" / "config.toml"
DEFAULT_ROOT = Path.home() / ".codex" / "mcp-tools"
NPM_ROOT = DEFAULT_ROOT / "npm"
REPORT_ROOT = DEFAULT_ROOT / "reports"
STATE_FILE = DEFAULT_ROOT / "mcp-localize-state.json"


@dataclass
class ManagedServer:
    name: str
    manager: str
    package: str
    requested: str | None
    command: str
    args: list[str]
    extra_args: list[str] = field(default_factory=list)
    bin_name: str | None = None
    source: str = "config"


@dataclass
class PackageInfo:
    server: ManagedServer
    installed_version: str | None = None
    remote_version: str | None = None
    status: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)
    release_notes: list[dict[str, str]] = field(default_factory=list)
    release_note_status: str = "not requested"
    config_needs_migration: bool = False
    suggested_command: str | None = None
    suggested_args: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit and localize Codex MCP servers from config.toml."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    parser.add_argument("--timeout", type=int, default=30)

    subparsers = parser.add_subparsers(dest="command", required=True)

    audit = subparsers.add_parser("audit", help="inspect configured MCP servers")
    audit.add_argument("--offline", action="store_true", help="skip remote metadata")
    audit.add_argument("--release-notes", action="store_true")
    audit.add_argument("--out", help="write a markdown report")
    audit.add_argument("--json-out", help="write a JSON report")
    audit.add_argument("--servers", nargs="*", help="limit to server names")

    install = subparsers.add_parser("install", help="install selected MCP servers")
    install.add_argument("--servers", nargs="+", required=True)
    install.add_argument("--dry-run", action="store_true")
    install.add_argument("--release-notes", action="store_true")

    snippets = subparsers.add_parser(
        "config-snippets", help="print local config.toml snippets"
    )
    snippets.add_argument("--offline", action="store_true", help="skip remote metadata")
    snippets.add_argument("--servers", nargs="*", help="limit to server names")

    args = parser.parse_args()
    config_path = Path(args.config).expanduser()
    root = Path(args.root).expanduser()

    if args.command == "audit":
        infos = audit_config(
            config_path,
            root,
            timeout=args.timeout,
            remote=not args.offline,
            release_notes=args.release_notes and not args.offline,
            only=args.servers,
        )
        report = render_markdown(infos)
        print(report)
        if args.out:
            out_path = Path(args.out).expanduser()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(report, encoding="utf-8")
        if args.json_out:
            json_path = Path(args.json_out).expanduser()
            json_path.parent.mkdir(parents=True, exist_ok=True)
            json_path.write_text(
                json.dumps([info_to_json(i) for i in infos], indent=2),
                encoding="utf-8",
            )
        return 0

    if args.command == "install":
        infos = audit_config(
            config_path,
            root,
            timeout=args.timeout,
            remote=True,
            release_notes=args.release_notes,
            only=args.servers,
        )
        selected = [i for i in infos if i.server.name in set(args.servers)]
        if not selected:
            print("No matching MCP servers found.", file=sys.stderr)
            return 2
        installed, failed = install_selected(
            selected,
            root,
            timeout=args.timeout,
            dry_run=args.dry_run,
        )
        if installed and not args.dry_run:
            save_state(root, installed)
        print(render_markdown(selected))
        print("\nRun `config-snippets` for first-time config.toml migration.")
        return 1 if failed else 0

    if args.command == "config-snippets":
        infos = audit_config(
            config_path,
            root,
            timeout=args.timeout,
            remote=not args.offline,
            release_notes=False,
            only=args.servers,
        )
        print(render_config_snippets(infos, root))
        return 0

    return 2


def audit_config(
    config_path: Path,
    root: Path,
    timeout: int,
    remote: bool,
    release_notes: bool,
    only: list[str] | None,
) -> list[PackageInfo]:
    config = load_toml(config_path)
    state = load_state(root)
    servers = discover_servers(config, state)
    if only:
        wanted = set(only)
        servers = [s for s in servers if s.name in wanted]

    infos: list[PackageInfo] = []
    for server in servers:
        info = PackageInfo(server=server)
        info.config_needs_migration = server.source == "config"
        try:
            info.installed_version = get_installed_version(server, root, timeout)
        except Exception as exc:  # noqa: BLE001
            info.errors.append(f"installed-version lookup failed: {exc}")
        if remote:
            try:
                if server.manager == "npm":
                    info.metadata = npm_metadata(server.package, timeout)
                    info.remote_version = info.metadata.get("version")
                elif server.manager == "uv":
                    info.metadata = pypi_metadata(server.package, timeout)
                    info.remote_version = info.metadata.get("version")
            except Exception as exc:  # noqa: BLE001
                info.errors.append(f"remote metadata lookup failed: {exc}")
        else:
            info.release_note_status = "offline audit; remote metadata skipped"

        info.status = status_for(info.installed_version, info.remote_version)
        info.suggested_command, info.suggested_args = suggested_command(
            server, root, info.metadata
        )

        if release_notes:
            collect_release_notes(info, timeout)

        infos.append(info)
    return infos


def load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("rb") as fh:
        return tomllib.load(fh)


def load_state(root: Path) -> dict[str, Any]:
    state_path = root / "mcp-localize-state.json"
    if not state_path.exists():
        return {"servers": {}}
    return json.loads(state_path.read_text(encoding="utf-8"))


def discover_servers(config: dict[str, Any], state: dict[str, Any]) -> list[ManagedServer]:
    found: dict[str, ManagedServer] = {}
    mcp_servers = config.get("mcp_servers", {})
    if not isinstance(mcp_servers, dict):
        return []

    for name, value in mcp_servers.items():
        if not isinstance(value, dict):
            continue
        server = classify_from_config(name, value)
        if server:
            found[name] = server

    for name, value in state.get("servers", {}).items():
        if name in found or not isinstance(value, dict):
            continue
        manager = value.get("manager")
        package = value.get("package")
        if manager and package:
            found[name] = ManagedServer(
                name=name,
                manager=manager,
                package=package,
                requested=value.get("requested"),
                command=value.get("command", ""),
                args=value.get("args", []),
                extra_args=value.get("extra_args", []),
                bin_name=value.get("bin_name"),
                source="state",
            )

    return list(found.values())


def classify_from_config(name: str, config: dict[str, Any]) -> ManagedServer | None:
    command = str(config.get("command", ""))
    args = [str(a) for a in config.get("args", [])]
    actual, actual_args = unwrap_cmd(command, args)
    base = command_base(actual).lower()

    if base == "npx":
        return classify_npx(name, command, args, actual_args)
    if base == "uvx":
        return classify_uvx(name, command, args, actual_args)
    return None


def unwrap_cmd(command: str, args: list[str]) -> tuple[str, list[str]]:
    if command_base(command).lower() in {"cmd", "cmd.exe"} and len(args) >= 2:
        if args[0].lower() in {"/c", "/k"}:
            return args[1], args[2:]
    return command, args


def command_base(command: str) -> str:
    return Path(command.strip("'\"")).name


def classify_npx(
    name: str, command: str, args: list[str], actual_args: list[str]
) -> ManagedServer | None:
    pkg_index = first_package_arg(actual_args)
    if pkg_index is None:
        return None
    spec = actual_args[pkg_index]
    package, requested = split_npm_spec(spec)
    return ManagedServer(
        name=name,
        manager="npm",
        package=package,
        requested=requested,
        command=command,
        args=args,
        extra_args=actual_args[pkg_index + 1 :],
        source="config",
    )


def classify_uvx(
    name: str, command: str, args: list[str], actual_args: list[str]
) -> ManagedServer | None:
    pkg_index = first_package_arg(actual_args)
    if pkg_index is None:
        return None
    spec = actual_args[pkg_index]
    package, requested = split_uv_spec(spec)
    return ManagedServer(
        name=name,
        manager="uv",
        package=package,
        requested=requested,
        command=command,
        args=args,
        extra_args=actual_args[pkg_index + 1 :],
        source="config",
    )


def first_package_arg(args: list[str]) -> int | None:
    skip_next_for = {
        "--cache",
        "--prefix",
        "--userconfig",
        "--registry",
        "--package",
        "--from",
        "--python",
        "--with",
        "--index-url",
        "--extra-index-url",
    }
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in {"-y", "--yes", "--quiet", "--no"}:
            i += 1
            continue
        if arg in skip_next_for:
            i += 2
            continue
        if arg.startswith("--") and "=" not in arg:
            i += 1
            continue
        if arg.startswith("-") and not arg.startswith("@"):
            i += 1
            continue
        return i
    return None


def split_npm_spec(spec: str) -> tuple[str, str | None]:
    if spec.startswith("@"):
        slash = spec.find("/")
        last_at = spec.rfind("@")
        if slash != -1 and last_at > slash:
            return spec[:last_at], spec[last_at + 1 :]
        return spec, None
    if "@" in spec:
        package, requested = spec.rsplit("@", 1)
        return package, requested
    return spec, None


def split_uv_spec(spec: str) -> tuple[str, str | None]:
    if "==" in spec:
        package, requested = spec.split("==", 1)
        return package, requested
    return spec, None


def get_installed_version(
    server: ManagedServer, root: Path, timeout: int
) -> str | None:
    if server.manager == "npm":
        package_json = npm_package_json_path(root, server.package)
        if package_json.exists():
            data = json.loads(package_json.read_text(encoding="utf-8"))
            return data.get("version")
        return None

    if server.manager == "uv":
        return uv_tool_versions(timeout).get(package_key(server.package))

    return None


def npm_package_json_path(root: Path, package: str) -> Path:
    return root / "npm" / "node_modules" / Path(package) / "package.json"


def uv_tool_versions(timeout: int) -> dict[str, str]:
    output = run_text(["uv", "tool", "list"], timeout=timeout)
    return parse_uv_tool_list(output)


def parse_uv_tool_list(output: str) -> dict[str, str]:
    versions: dict[str, str] = {}
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("-"):
            continue
        match = re.match(r"^(?P<package>\S+)\s+v?(?P<version>\d[^\s]*)", line)
        if match:
            versions[package_key(match.group("package"))] = match.group("version")
    return versions


def package_key(package: str) -> str:
    base = package.split("[", 1)[0]
    return re.sub(r"[-_.]+", "-", base).lower()


def npm_metadata(package: str, timeout: int) -> dict[str, Any]:
    raw = run_text(
        [
            "npm",
            "view",
            package,
            "version",
            "dist-tags",
            "repository",
            "homepage",
            "description",
            "bin",
            "time",
            "--json",
        ],
        timeout=timeout,
    )
    data = json.loads(raw)
    if isinstance(data, list) and data:
        merged: dict[str, Any] = {}
        keys = ["version", "dist-tags", "repository", "homepage", "description", "bin", "time"]
        for key, value in zip(keys, data, strict=False):
            merged[key] = value
        return merged
    if isinstance(data, dict):
        return data
    return {}


def pypi_metadata(package: str, timeout: int) -> dict[str, Any]:
    url = f"https://pypi.org/pypi/{urllib.parse.quote(package)}/json"
    data = fetch_json(url, timeout)
    info = data.get("info", {})
    return {
        "version": info.get("version"),
        "description": info.get("summary") or info.get("description"),
        "homepage": info.get("home_page"),
        "repository": pick_project_url(info.get("project_urls", {})),
        "project_urls": info.get("project_urls", {}),
        "releases": data.get("releases", {}),
    }


def pick_project_url(project_urls: dict[str, str]) -> str | None:
    for key in ["Repository", "Source", "Source Code", "Homepage", "Changelog"]:
        if key in project_urls:
            return project_urls[key]
    for value in project_urls.values():
        return value
    return None


def fetch_json(url: str, timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "codex-mcp-localize"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def run_text(
    command: list[str],
    timeout: int,
    cwd: Path | None = None,
    check: bool = True,
) -> str:
    resolved = command[:]
    resolved[0] = resolve_executable(resolved[0])
    process = subprocess.Popen(
        resolved,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        kill_process_tree(process)
        stdout, stderr = process.communicate()
        output = ((stdout or "") + (stderr or "")).strip()
        if output:
            raise TimeoutError(f"{command} timed out after {timeout}s: {output}") from exc
        raise TimeoutError(f"{command} timed out after {timeout}s") from exc
    output = (stdout or "") + (stderr or "")
    if check and process.returncode != 0:
        raise RuntimeError(output.strip() or f"command failed: {command}")
    return output.strip()


def kill_process_tree(process: subprocess.Popen[str]) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            text=True,
            capture_output=True,
            check=False,
        )
    else:
        process.kill()


def resolve_executable(name: str) -> str:
    if Path(name).is_absolute():
        return name
    found = shutil.which(name)
    if found:
        return found
    if os.name == "nt" and "." not in Path(name).name:
        for suffix in [".cmd", ".exe", ".bat"]:
            found = shutil.which(name + suffix)
            if found:
                return found
    return name


def status_for(installed: str | None, remote: str | None) -> str:
    if not installed and remote:
        return "not-installed"
    if installed and remote:
        if normalize_version(installed) == normalize_version(remote):
            return "current"
        return "update-available"
    if installed and not remote:
        return "installed-remote-unknown"
    return "unknown"


def normalize_version(version: str) -> str:
    return version.strip().lstrip("v")


def suggested_command(
    server: ManagedServer, root: Path, metadata: dict[str, Any]
) -> tuple[str | None, list[str]]:
    if server.manager == "npm":
        bin_name = server.bin_name or choose_npm_bin(server.package, metadata.get("bin"))
        command = str(root / "npm" / "node_modules" / ".bin" / f"{bin_name}.cmd")
        return command, server.extra_args

    if server.manager == "uv":
        bin_name = server.bin_name or server.package
        bin_dir = uv_tool_bin_dir()
        command = str(bin_dir / f"{bin_name}.exe")
        return command, server.extra_args

    return None, []


def choose_npm_bin(package: str, bin_meta: Any) -> str:
    if isinstance(bin_meta, str):
        return package_leaf(package)
    if isinstance(bin_meta, dict) and bin_meta:
        first = next(iter(bin_meta.keys()))
        return str(first)
    return package_leaf(package)


def package_leaf(package: str) -> str:
    return package.rsplit("/", 1)[-1]


def uv_tool_bin_dir() -> Path:
    override = os.environ.get("UV_TOOL_BIN_DIR")
    if override:
        return Path(override)
    return Path.home() / ".local" / "bin"


def collect_release_notes(info: PackageInfo, timeout: int) -> None:
    repo_url = repo_url_from_metadata(info.metadata)
    if not repo_url:
        info.release_note_status = "no repository URL in package metadata"
        return

    github = parse_github_repo(repo_url)
    if not github:
        info.release_note_status = f"repository is not a GitHub releases URL: {repo_url}"
        return

    owner, repo = github
    try:
        releases = fetch_json(
            f"https://api.github.com/repos/{owner}/{repo}/releases?per_page=20",
            timeout=timeout,
        )
    except urllib.error.HTTPError as exc:
        info.release_note_status = f"GitHub releases lookup failed: HTTP {exc.code}"
        return
    except Exception as exc:  # noqa: BLE001
        info.release_note_status = f"GitHub releases lookup failed: {exc}"
        return

    if not isinstance(releases, list) or not releases:
        info.release_note_status = f"no GitHub releases found at {owner}/{repo}"
        return

    selected = filter_releases(releases, info.installed_version, info.remote_version)
    info.release_notes = [
        {
            "tag": str(r.get("tag_name") or r.get("name") or ""),
            "name": str(r.get("name") or ""),
            "published_at": str(r.get("published_at") or ""),
            "url": str(r.get("html_url") or ""),
            "summary": summarize_release_body(str(r.get("body") or "")),
        }
        for r in selected
    ]
    if info.release_notes:
        info.release_note_status = "GitHub releases found"
    else:
        info.release_note_status = "GitHub releases found, none mapped to version range"


def repo_url_from_metadata(metadata: dict[str, Any]) -> str | None:
    repository = metadata.get("repository")
    if isinstance(repository, dict):
        url = repository.get("url")
        if url:
            return str(url)
    if isinstance(repository, str):
        return repository
    homepage = metadata.get("homepage")
    if homepage:
        return str(homepage)
    return None


def parse_github_repo(url: str) -> tuple[str, str] | None:
    cleaned = url.strip().removeprefix("git+").removesuffix(".git")
    cleaned = cleaned.replace("git://github.com/", "https://github.com/")
    cleaned = cleaned.replace("git@github.com:", "https://github.com/")
    match = re.search(r"github\.com[:/](?P<owner>[^/\s]+)/(?P<repo>[^/#?\s]+)", cleaned)
    if not match:
        return None
    return match.group("owner"), match.group("repo").removesuffix(".git")


def filter_releases(
    releases: list[dict[str, Any]],
    installed: str | None,
    remote: str | None,
) -> list[dict[str, Any]]:
    if not installed or not remote:
        return releases[:5]
    low = semver_tuple(installed)
    high = semver_tuple(remote)
    if not low or not high:
        return releases[:5]
    selected: list[dict[str, Any]] = []
    for release in releases:
        tag = str(release.get("tag_name") or "")
        version = semver_tuple(tag)
        if version and low < version <= high:
            selected.append(release)
    return selected[:8]


def semver_tuple(value: str) -> tuple[int, int, int] | None:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def summarize_release_body(body: str) -> str:
    if not body.strip():
        return "(no release body)"
    lines = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        if len(line) > 180:
            line = line[:177] + "..."
        lines.append(line)
        if len(lines) >= 6:
            break
    return "\n".join(lines)


def install_one(info: PackageInfo, root: Path, timeout: int, dry_run: bool) -> None:
    server = info.server
    version = info.remote_version or server.requested
    if not version or version == "latest":
        raise RuntimeError(f"Cannot install {server.name}: remote version is unknown")

    if server.manager == "npm":
        NPM_ROOT.mkdir(parents=True, exist_ok=True)
        package_json = NPM_ROOT / "package.json"
        if not package_json.exists():
            package_json.write_text(
                json.dumps(
                    {
                        "private": True,
                        "name": "codex-mcp-tools",
                        "version": "0.0.0",
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        command = ["npm", "install", "--save-exact", f"{server.package}@{version}"]
        print("$ " + " ".join(command))
        if not dry_run:
            run_text(command, timeout=timeout * 4, cwd=NPM_ROOT)
            info.installed_version = get_installed_version(server, root, timeout)
        return

    if server.manager == "uv":
        if versions_equal(info.installed_version, version):
            print(
                f"# {server.name}: {server.package}=={version} already installed; "
                "skipping uv tool install."
            )
            info.status = "current"
            return
        command = ["uv", "tool", "install", f"{server.package}=={version}"]
        print("$ " + " ".join(command))
        if not dry_run:
            run_text(command, timeout=timeout * 4)
            info.installed_version = version
            info.status = status_for(info.installed_version, info.remote_version)
        return

    raise RuntimeError(f"Unsupported manager: {server.manager}")


def versions_equal(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    return normalize_version(left) == normalize_version(right)


def install_selected(
    selected: list[PackageInfo],
    root: Path,
    timeout: int,
    dry_run: bool,
) -> tuple[list[PackageInfo], list[PackageInfo]]:
    installed: list[PackageInfo] = []
    failed: list[PackageInfo] = []
    for info in selected:
        try:
            install_one(info, root, timeout=timeout, dry_run=dry_run)
        except Exception as exc:  # noqa: BLE001
            info.status = "install-failed"
            info.errors.append(f"install failed: {exc}")
            failed.append(info)
            print(f"{info.server.name}: install failed: {exc}", file=sys.stderr)
            continue
        installed.append(info)
    return installed, failed


def save_state(root: Path, infos: list[PackageInfo]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    state = load_state(root)
    servers = state.setdefault("servers", {})
    for info in infos:
        server = info.server
        suggested_cmd, suggested_args = suggested_command(server, root, info.metadata)
        servers[server.name] = {
            "manager": server.manager,
            "package": server.package,
            "requested": info.remote_version or server.requested,
            "installed_version": info.installed_version,
            "bin_name": command_bin_name(suggested_cmd),
            "command": suggested_cmd,
            "args": suggested_args,
            "extra_args": server.extra_args,
            "updated_at": dt.datetime.now(dt.UTC).isoformat(),
        }
    (root / "mcp-localize-state.json").write_text(
        json.dumps(state, indent=2), encoding="utf-8"
    )


def command_bin_name(command: str | None) -> str | None:
    if not command:
        return None
    name = Path(command).name
    for suffix in [".cmd", ".exe", ".bat"]:
        if name.lower().endswith(suffix):
            return name[: -len(suffix)]
    return name


def render_markdown(infos: list[PackageInfo]) -> str:
    lines = [
        "# Codex MCP Localize Audit",
        "",
        f"Generated: {dt.datetime.now().isoformat(timespec='seconds')}",
        "",
        "| Server | Manager | Package | Requested | Installed | Remote | Status | Config |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for info in infos:
        lines.append(
            "| {name} | {manager} | {package} | {requested} | {installed} | "
            "{remote} | {status} | {config} |".format(
                name=info.server.name,
                manager=info.server.manager,
                package=info.server.package,
                requested=info.server.requested or "",
                installed=info.installed_version or "",
                remote=info.remote_version or "",
                status=info.status,
                config="needs migration" if info.config_needs_migration else "local/state",
            )
        )

    for info in infos:
        lines.extend(["", f"## {info.server.name}", ""])
        lines.append(f"- Package: `{info.server.package}`")
        lines.append(f"- Manager: `{info.server.manager}`")
        lines.append(f"- Suggested command: `{info.suggested_command or ''}`")
        if info.suggested_args:
            lines.append(f"- Suggested args: `{json.dumps(info.suggested_args)}`")
        lines.append(f"- Release notes: {info.release_note_status}")
        if info.metadata.get("homepage"):
            lines.append(f"- Homepage: {info.metadata['homepage']}")
        repo = repo_url_from_metadata(info.metadata)
        if repo:
            lines.append(f"- Repository: {repo}")
        for release in info.release_notes:
            lines.extend(
                [
                    "",
                    f"### {release['tag']} {release['name']}".strip(),
                    "",
                    f"- Published: {release['published_at']}",
                    f"- URL: {release['url']}",
                    "",
                    indent_block(release["summary"]),
                ]
            )
        if info.errors:
            lines.append("")
            lines.append("Errors:")
            for error in info.errors:
                lines.append(f"- {error}")

    return "\n".join(lines).rstrip() + "\n"


def indent_block(text: str) -> str:
    return "\n".join(f"> {line}" for line in text.splitlines())


def render_config_snippets(infos: list[PackageInfo], root: Path) -> str:
    blocks = [
        "# Suggested config.toml MCP stanzas",
        "# Back up config.toml before applying. Preserve existing env subtables.",
        "",
    ]
    for info in infos:
        command, args = suggested_command(info.server, root, info.metadata)
        blocks.append(f"[mcp_servers.{info.server.name}]")
        blocks.append('type = "stdio"')
        blocks.append(f"command = {toml_string(command or '')}")
        blocks.append(f"args = {toml_array(args)}")
        blocks.append("startup_timeout_sec = 120")
        blocks.append("")
    return "\n".join(blocks)


def toml_string(value: str) -> str:
    return json.dumps(value)


def toml_array(values: list[str]) -> str:
    return "[" + ", ".join(json.dumps(v) for v in values) + "]"


def info_to_json(info: PackageInfo) -> dict[str, Any]:
    return {
        "server": info.server.__dict__,
        "installed_version": info.installed_version,
        "remote_version": info.remote_version,
        "status": info.status,
        "release_note_status": info.release_note_status,
        "release_notes": info.release_notes,
        "config_needs_migration": info.config_needs_migration,
        "suggested_command": info.suggested_command,
        "suggested_args": info.suggested_args,
        "errors": info.errors,
    }


if __name__ == "__main__":
    raise SystemExit(main())
