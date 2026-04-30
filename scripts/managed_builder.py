#!/usr/bin/env python3
"""
Managed Builder — per-module cloud implementation via Anthropic Managed Agents API.

The cloud path and local-fallback path share one interface: both receive a single
approved contract and CASE_FACTS.md and produce source files + tests for that module.
The sandbox is where it runs, not what it builds.

Setup (run once):
    python scripts/managed_builder.py --setup
    # Prints export statements; add to .env

Runtime (per module):
    python scripts/managed_builder.py \
      --contract docs/contracts/<module>.md \
      --case-facts docs/CASE_FACTS.md \
      --target .
    # Add --allow-sensitive-context only after human review.

Environment variables (required at runtime):
    ANTHROPIC_API_KEY                  — host-only; never forwarded to sandbox
    MANAGED_BUILDER_ENVIRONMENT_ID     — set by --setup
    MANAGED_BUILDER_AGENT_ID           — set by --setup
    MANAGED_BUILDER_AGENT_VERSION      — set by --setup
"""

import argparse
import os
import re
import sys
from pathlib import Path

import anthropic

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass


# Patterns that may indicate credentials in input files.
# This is a hard block unless --allow-sensitive-context is passed.
_CREDENTIAL_RE = re.compile(
    r"(sk-ant-|ghp_|Bearer\s+[A-Za-z0-9_\-]{16,}"
    r"|api_key\s*=\s*['\"][^'\"]{8,}['\"]"
    r"|password\s*=\s*['\"][^'\"]{4,}['\"])",
    re.IGNORECASE,
)

# Files owned by the orchestrator — excluded from sandbox extraction.
# The sandbox must not write these; the orchestrator manages them locally.
_ORCHESTRATOR_FILES = {
    ".env",
    ".mcp.json",
    "ACTIVE_RISK_REGISTER.md",
    "STATE_HANDOFF.md",
    "STORY.md",
}


# ── helpers ──────────────────────────────────────────────────────────────────


def _atomic_write(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    assert tmp.stat().st_size > 0, f"Atomic write guard: empty file at {tmp}"
    os.replace(tmp, path)


def _read_required_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        sys.exit(f"ERROR: {name} is not set. Run --setup first.")
    return val


def _block_if_credentials(label: str, content: str, allow_sensitive_context: bool) -> None:
    matches = _CREDENTIAL_RE.findall(content)
    if matches:
        if allow_sensitive_context:
            print(
                f"\n  [WARNING] {label} may contain credentials — matched: {matches[:2]}\n"
                "  Continuing because --allow-sensitive-context was provided.\n",
                file=sys.stderr,
            )
            return
        print(
            f"\nERROR: {label} may contain credentials — matched: {matches[:2]}\n"
            "Refusing to send this content to the cloud sandbox.\n"
            "Move secrets to environment variables or rerun with --allow-sensitive-context.\n",
            file=sys.stderr,
        )
        sys.exit(2)


# ── setup (run once) ──────────────────────────────────────────────────────────


def cmd_setup() -> None:
    client = anthropic.Anthropic()

    print("Creating Managed Builder environment…")
    env = client.beta.environments.create(
        name="factory-builder-env",
        extra_headers={"anthropic-beta": "managed-agents-2026-04-01"},
    )
    env_id = env.id
    print(f"  environment: {env_id}")

    print("Creating Managed Builder agent…")
    agent = client.beta.agents.create(
        name="factory-builder",
        model="claude-sonnet-4-6",
        tools=[{"type": "agent_toolset_20260401"}],
        system=(
            "You are the Implementation Engine for the Business Idea Factory.\n"
            "You receive one approved module contract and CASE_FACTS. Implement that module only.\n"
            "\n"
            "Non-negotiable rules:\n"
            "- Implement exactly what the contract specifies. No extra scope.\n"
            "- Monetary values: decimal.Decimal only. Never float.\n"
            "- Secrets: os.environ only. Write .env.example with placeholder values, never real values.\n"
            "- Tests alongside implementation. Line coverage >= 80%.\n"
            "- Do not implement anything in the Out of Scope section of CASE_FACTS.\n"
            "\n"
            "File creation rule (critical for extraction):\n"
            "- Use the write tool for every file you create. Do not use bash redirects or the edit tool.\n"
            "- The extraction layer only captures explicit write tool calls. Anything else is lost.\n"
            "\n"
            "Do not write STORY.md. The orchestrator manages that file."
        ),
        extra_headers={"anthropic-beta": "managed-agents-2026-04-01"},
    )
    agent_id = agent.id
    agent_version = agent.version
    print(f"  agent:       {agent_id}")
    print(f"  version:     {agent_version}")

    print(
        "\nIMPORTANT: the system prompt is baked into this agent version.\n"
        "If you re-run --setup after a system prompt change, update .env with the new IDs.\n"
    )
    print("Add these to your .env:\n")
    print(f"export MANAGED_BUILDER_ENVIRONMENT_ID={env_id}")
    print(f"export MANAGED_BUILDER_AGENT_ID={agent_id}")
    print(f"export MANAGED_BUILDER_AGENT_VERSION={agent_version}")


# ── runtime ───────────────────────────────────────────────────────────────────


def cmd_run(
    contract_path: Path,
    case_facts_path: Path,
    target: Path,
    allow_sensitive_context: bool,
) -> None:
    if not contract_path.exists():
        sys.exit(f"ERROR: contract not found at {contract_path}")
    if not case_facts_path.exists():
        sys.exit(f"ERROR: CASE_FACTS.md not found at {case_facts_path}")

    contract = contract_path.read_text(encoding="utf-8")
    case_facts = case_facts_path.read_text(encoding="utf-8")

    if "Status: approved" not in contract and "`approved`" not in contract:
        sys.exit(f"ERROR: contract is not approved: {contract_path}")

    _block_if_credentials("contract", contract, allow_sensitive_context)
    _block_if_credentials("CASE_FACTS.md", case_facts, allow_sensitive_context)

    env_id = _read_required_env("MANAGED_BUILDER_ENVIRONMENT_ID")
    agent_id = _read_required_env("MANAGED_BUILDER_AGENT_ID")
    agent_version = _read_required_env("MANAGED_BUILDER_AGENT_VERSION")

    client = anthropic.Anthropic()

    initial_message = (
        "=== CONTRACT (approved — implement exactly this module) ===\n\n"
        f"{contract}\n\n"
        "=== CASE FACTS (verbatim — binding constraints) ===\n\n"
        f"{case_facts}\n\n"
        "=== INSTRUCTION ===\n"
        f"Target directory: {target.resolve()}\n"
        "Implement the contract above. Write source files and tests using the write tool.\n"
        "Do not use bash redirects. Do not write STORY.md. Do not exceed the contract scope."
    )

    print(f"Starting Managed Builder session (agent {agent_id} v{agent_version})…")
    print(f"  contract: {contract_path}")

    extracted_files: dict[str, str] = {}

    # Stream-first: open stream before sending first message to avoid missing early events.
    with client.beta.sessions.events.stream(
        agent_id=agent_id,
        agent_version=agent_version,
        environment_id=env_id,
        messages=[{"role": "user", "content": initial_message}],
        extra_headers={"anthropic-beta": "managed-agents-2026-04-01"},
    ) as stream:
        for event in stream:
            _handle_event(event, extracted_files)

    print(f"\nSession complete. Extracted {len(extracted_files)} file(s) from sandbox.")

    written = 0
    target_resolved = target.resolve()
    for rel_path, content in extracted_files.items():
        dest = target / rel_path.lstrip("/")
        # Reject path traversal — sandbox must not write outside target.
        try:
            dest.resolve().relative_to(target_resolved)
        except ValueError:
            print(f"  [BLOCKED] path escapes target directory: {rel_path}", file=sys.stderr)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(dest, content)
        print(f"  wrote: {dest.relative_to(target)}")
        written += 1

    if written == 0:
        print(
            "WARNING: no files were extracted from the agent session.\n"
            "  The agent may have used bash redirects instead of the write tool.\n"
            "  Check the session log above for details.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"\nManaged Builder complete — {written} file(s) written to {target}")


def _handle_event(event: object, extracted: dict[str, str]) -> None:
    event_type = getattr(event, "type", None)

    if event_type == "agent.tool_use":
        tool_name = getattr(event, "name", None)
        tool_input = getattr(event, "input", {}) or {}

        if tool_name in ("write", "write_file"):
            path = tool_input.get("path") or tool_input.get("file_path")
            content = tool_input.get("content") or tool_input.get("file_content", "")
            if not path:
                return
            basename = Path(path).name
            if basename in _ORCHESTRATOR_FILES:
                print(f"  [skip] {path} — orchestrator-managed file")
                return
            if path in extracted:
                print(f"  [overwrite] {path} — duplicate write, keeping last version")
            extracted[path] = content
            print(f"  [extract] {path} ({len(content)} chars)")

    elif event_type == "agent.message":
        content = getattr(event, "content", None)
        if isinstance(content, list):
            for block in content:
                if getattr(block, "type", None) == "text":
                    text = getattr(block, "text", "").strip()
                    if text:
                        print(f"  [agent] {text[:200]}")
        elif isinstance(content, str) and content.strip():
            print(f"  [agent] {content.strip()[:200]}")

    elif event_type == "session.status_idle":
        stop = getattr(event, "stop_reason", None)
        stop_type = getattr(stop, "type", None) if stop else None
        if stop_type and stop_type != "requires_action":
            print(f"  [session idle] stop_reason={stop_type}")

    elif event_type == "session.status_terminated":
        reason = getattr(event, "reason", "unknown")
        print(f"  [session terminated] reason={reason}")

    elif event_type and event_type.startswith("error"):
        print(f"  [error event] {event}", file=sys.stderr)


# ── entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Managed Builder — per-module cloud implementation"
    )
    parser.add_argument(
        "--setup", action="store_true", help="Create environment + agent (run once)"
    )
    parser.add_argument(
        "--contract", type=Path, help="Path to the approved module contract (.md)"
    )
    parser.add_argument(
        "--case-facts", type=Path, dest="case_facts", help="Path to CASE_FACTS.md"
    )
    parser.add_argument(
        "--target", type=Path, help="Target directory for extracted files"
    )
    parser.add_argument(
        "--allow-sensitive-context",
        action="store_true",
        help="Allow sending input files that match credential-like patterns",
    )

    args = parser.parse_args()

    if args.setup:
        cmd_setup()
    elif args.contract and args.case_facts and args.target:
        cmd_run(
            args.contract,
            args.case_facts,
            args.target,
            args.allow_sensitive_context,
        )
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
