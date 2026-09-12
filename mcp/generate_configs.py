"""
Generate host configurations from mcp/manifest.yaml.

Outputs
  .mcp.json                       Claude Code project MCP servers
  .agents/mcp.json                Antigravity / generic host MCP servers
  .agents/agents/<agent>.md       tools: frontmatter + "MCP TOOL ACCESS" block
                                  (between the AUTOGEN markers only)

Usage:  python mcp/generate_configs.py [--check]
"""

from __future__ import annotations

import json
import re
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


ABSOLUTE = False  # set by --absolute; default emits paths relative to the repo root


def _python() -> str:
    win = ROOT / ".venv" / "Scripts" / "python.exe"
    nix = ROOT / ".venv" / "bin" / "python"
    chosen = win if win.exists() or not nix.exists() else nix
    return chosen.as_posix() if ABSOLUTE else chosen.relative_to(ROOT).as_posix()


def _fill(value: Any) -> Any:
    if isinstance(value, str):
        root = ROOT.as_posix() if ABSOLUTE else "."
        out = value.replace("{python}", _python()).replace("{root}/", "" if not ABSOLUTE else root + "/")
        return out.replace("{root}", root)
    if isinstance(value, list):
        return [_fill(v) for v in value]
    if isinstance(value, dict):
        return {k: _fill(v) for k, v in value.items()}
    return value


def server_config(manifest: Dict[str, Any], names: List[str] | None = None) -> Dict[str, Any]:
    """Hosts launch stdio servers with cwd = repository root, so relative paths stay portable."""
    servers = {}
    for name, spec in manifest["servers"].items():
        if names and name not in names:
            continue
        entry = {"command": _fill(spec["command"]), "args": _fill(spec.get("args", []))}
        if spec.get("env"):
            entry["env"] = _fill(spec["env"])
        servers[name] = entry
    return {"mcpServers": servers}


def agent_tool_names(manifest: Dict[str, Any], agent: str) -> List[str]:
    spec = manifest["agents"][agent]
    names: List[str] = []
    for group in spec["quant_server_groups"]:
        names += [f"mcp__quant-server__{t}" for t in manifest["quant_server_tools"][group]]
    return names


def tool_access_block(manifest: Dict[str, Any], agent: str) -> str:
    spec = manifest["agents"][agent]
    lines = [BEGIN, "", "## MCP TOOL ACCESS", "",
             f"Filesystem access: **{spec['filesystem_access']}**. Servers: {', '.join(spec['servers'])}.", "",
             "| Server | Tools available to this agent |", "|---|---|"]
    for group in spec["quant_server_groups"]:
        tools = ", ".join(f"`{t}`" for t in manifest["quant_server_tools"][group])
        lines.append(f"| quant-server ({group}) | {tools} |")
    for s in spec["servers"]:
        if s != "quant-server":
            lines.append(f"| {s} | {manifest['servers'][s]['description']} |")
    forbidden = ", ".join(f"`*{p}*`" for p in manifest["forbidden_tool_patterns"])
    lines += ["", f"Never available through MCP to any agent: {forbidden}. Live orders go through the Central Risk Engine and a human-approved deployment gate only.", "", END]
    return "\n".join(lines)


def update_agent_file(manifest: Dict[str, Any], agent: str, check: bool) -> bool:
    path = ROOT / manifest["agents"][agent]["file"]
    text = path.read_text(encoding="utf-8-sig")
    original = text

    # 1. tools: frontmatter line -> keep host-native tools, replace mcp__quant-server__* set
    m = re.search(r"^tools:\s*(.*)$", text, flags=re.M)
    if m:
        existing = [t.strip() for t in m.group(1).split(",") if t.strip()]
        kept = [t for t in existing if not t.startswith("mcp__quant-server__")]
        new_line = "tools: " + ", ".join(kept + agent_tool_names(manifest, agent))
        text = text[: m.start()] + new_line + text[m.end():]

    # 2. autogen block
    block = tool_access_block(manifest, agent)
    if BEGIN in text and END in text:
        text = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), lambda _: block, text, flags=re.S)
    else:
        text = text.rstrip() + "\n\n---\n\n" + block + "\n"

    changed = text != original
    if changed and not check:
        path.write_text(text, encoding="utf-8")
    return changed


def main(argv: List[str]) -> int:
    global ABSOLUTE
    check = "--check" in argv
    ABSOLUTE = "--absolute" in argv
    manifest = load_manifest()
    outputs = {
        ROOT / ".mcp.json": server_config(manifest),
        ROOT / ".agents" / "mcp.json": server_config(manifest),
    }
    drift = False
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
        if update_agent_file(manifest, agent, check):
            drift = True
            if not check:
                print(f"updated {manifest['agents'][agent]['file']}")
    if check:
        print("configs out of date" if drift else "configs up to date")
        return 1 if drift else 0
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
