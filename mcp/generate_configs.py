"""
Generate every host configuration from mcp/manifest.yaml.

Outputs
  .mcp.json                     Claude Code project servers (env-expandable paths)
  .agents/mcp.json              Antigravity / generic hosts (resolved paths)
  <agent files>                 tools: frontmatter (mcp__* grants) and the
                                AUTOGEN "MCP TOOL ACCESS" block, for every file
                                listed under agents.<name>.files, in-repo or external

Usage:  python mcp/generate_configs.py [--check] [--no-sync]
  --check    exit 1 if any output would change (CI guard); writes nothing
  --no-sync  skip the post_generate projection (kit sync_plugin.py)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "mcp" / "manifest.yaml"
BEGIN = "<!-- AUTOGEN:MCP-TOOL-ACCESS:BEGIN (edit mcp/manifest.yaml, then run mcp/generate_configs.py) -->"
END = "<!-- AUTOGEN:MCP-TOOL-ACCESS:END -->"


def load_manifest() -> Dict[str, Any]:
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))


# ------------------------------------------------------------ placeholders
def _venv_python() -> str:
    win = ROOT / ".venv" / "Scripts" / "python.exe"
    nix = ROOT / ".venv" / "bin" / "python"
    return (win if win.exists() or not nix.exists() else nix).relative_to(ROOT).as_posix()


def external_values(manifest: Dict[str, Any], env_style: bool) -> Dict[str, str]:
    """Resolve {merg} / {merg_python}. env_style emits ${VAR:-default} for hosts that expand env vars."""
    ext = manifest["external"]
    merg = os.environ.get(ext["merg_root_env"], ext["merg_root_default"]).replace("\\", "/")
    mpy = os.environ.get(ext["merg_python_env"], ext["merg_python_default"]).replace("\\", "/")
    if env_style:
        return {
            "merg": f"${{{ext['merg_root_env']}:-{ext['merg_root_default']}}}",
            "merg_python": f"${{{ext['merg_python_env']}:-{ext['merg_python_default']}}}",
        }
    return {"merg": merg, "merg_python": mpy}


def fill(value: Any, ext: Dict[str, str]) -> Any:
    if isinstance(value, str):
        out = value.replace("{python}", _venv_python())
        out = out.replace("{root}/", "").replace("{root}", ".")
        out = out.replace("{merg_python}", ext["merg_python"]).replace("{merg}", ext["merg"])
        return out
    if isinstance(value, list):
        return [fill(v, ext) for v in value]
    if isinstance(value, dict):
        return {k: fill(v, ext) for k, v in value.items()}
    return value


def server_config(manifest: Dict[str, Any], env_style: bool = False) -> Dict[str, Any]:
    """Hosts launch stdio servers with cwd = repo root, so in-repo paths stay relative."""
    ext = external_values(manifest, env_style)
    servers = {}
    for name, spec in manifest["servers"].items():
        entry = {"command": fill(spec["command"], ext), "args": fill(spec.get("args", []), ext)}
        if spec.get("env"):
            entry["env"] = fill(spec["env"], ext)
        servers[name] = entry
    return {"mcpServers": servers}


# ------------------------------------------------------------- agent files
def agent_tool_names(manifest: Dict[str, Any], agent: str) -> List[str]:
    spec = manifest["agents"][agent]
    names: List[str] = []
    for server in spec["servers"]:
        groups = manifest["tool_groups"].get(server)
        if not groups:
            continue  # reference servers: host exposes them whole
        prefix = manifest["servers"][server]["tool_prefix"]
        for group in spec["groups"]:
            names += [prefix + t for t in groups.get(group, [])]
    return names


def managed_prefixes(manifest: Dict[str, Any]) -> List[str]:
    return [s["tool_prefix"] for s in manifest["servers"].values() if s.get("tool_prefix")]


def tool_access_block(manifest: Dict[str, Any], agent: str) -> str:
    spec = manifest["agents"][agent]
    lines = [BEGIN, "", "## MCP TOOL ACCESS", "",
             f"Filesystem access: **{spec['filesystem_access']}**. Servers: {', '.join(spec['servers'])}.", ""]
    if spec.get("note"):
        lines += [spec["note"], ""]
    lines += ["| Server | Tools available to this agent |", "|---|---|"]
    for server in spec["servers"]:
        groups = manifest["tool_groups"].get(server)
        if groups:
            for group in spec["groups"]:
                if groups.get(group):
                    lines.append(f"| {server} ({group}) | " + ", ".join(f"`{t}`" for t in groups[group]) + " |")
        else:
            lines.append(f"| {server} | {manifest['servers'][server]['description']} |")
    forbidden = ", ".join(f"`*{p}*`" for p in manifest["forbidden_tool_patterns"])
    lines += ["", f"Never available through MCP to any agent: {forbidden}. Live orders go through the Central Risk Engine and a human-approved deployment gate only.",
              "", "Generated from `mcp/manifest.yaml` in the Research_Quant_Bot repository; identical grants are written to every copy of this agent (repo `.agents/`, quant-bot-kit plugin, Antigravity).", "", END]
    return "\n".join(lines)


def resolve_agent_files(manifest: Dict[str, Any], agent: str) -> List[Path]:
    ext = external_values(manifest, env_style=False)
    out = []
    for f in manifest["agents"][agent]["files"]:
        f = f.replace("{merg}", ext["merg"])
        p = Path(f)
        out.append(p if p.is_absolute() else ROOT / p)
    return out


def render_agent_file(manifest: Dict[str, Any], agent: str, text: str) -> str:
    m = re.search(r"^tools:\s*(.*)$", text, flags=re.M)
    if m:
        existing = [t.strip() for t in m.group(1).split(",") if t.strip()]
        kept = [t for t in existing if not any(t.startswith(p) for p in managed_prefixes(manifest))]
        text = text[: m.start()] + "tools: " + ", ".join(kept + agent_tool_names(manifest, agent)) + text[m.end():]
    block = tool_access_block(manifest, agent)
    if BEGIN in text and END in text:
        text = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), lambda _: block, text, flags=re.S)
    else:
        text = text.rstrip() + "\n\n---\n\n" + block + "\n"
    return text


def update_agent_files(manifest: Dict[str, Any], agent: str, check: bool) -> List[Path]:
    changed = []
    for path in resolve_agent_files(manifest, agent):
        if not path.exists():
            print(f"skip (missing) {path}")
            continue
        original = path.read_text(encoding="utf-8-sig")
        rendered = render_agent_file(manifest, agent, original)
        if rendered != original:
            changed.append(path)
            if not check:
                path.write_text(rendered, encoding="utf-8")
    return changed


# ------------------------------------------------------------------- main
def main(argv: List[str]) -> int:
    check = "--check" in argv
    sync = "--no-sync" not in argv and not check
    manifest = load_manifest()
    drift = False

    outputs = {
        ROOT / ".mcp.json": server_config(manifest, env_style=True),
        ROOT / ".agents" / "mcp.json": server_config(manifest, env_style=False),
    }
    for path, data in outputs.items():
        rendered = json.dumps(data, indent=2) + "\n"
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current != rendered:
            drift = True
            if not check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(rendered, encoding="utf-8")
                print(f"wrote {path.relative_to(ROOT)}")

    for agent in manifest["agents"]:
        for p in update_agent_files(manifest, agent, check):
            drift = True
            if not check:
                print(f"updated {p}")

    if check:
        print("configs out of date" if drift else "configs up to date")
        return 1 if drift else 0

    if sync:
        ext = external_values(manifest, env_style=False)
        for step in manifest.get("post_generate", []):
            cmd = [fill(step["command"], ext)] + fill(step.get("args", []), ext)
            if not Path(cmd[-1]).exists():
                print(f"skip sync (missing) {cmd[-1]}")
                continue
            print("sync:", " ".join(cmd))
            res = subprocess.run(cmd, capture_output=True, text=True)
            print(res.stdout.strip()[-1500:])
            if res.returncode != 0:
                print(res.stderr.strip()[-800:])
                return res.returncode
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
