#!/usr/bin/env python3
"""
auto_watcher.py — optional HEAVY-kit helper.

Watches docs/contracts/CONTRACT_INDEX.md for this completion signal:
    ## Status: APPROVED_FOR_BUILD

When the signal appears, runs managed_builder.py once for each approved module
contract in docs/contracts/. This is a convenience wrapper only; reviewer and
integrator gates still run through Claude Code.
"""

import logging
import os
import subprocess
import sys
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_DIR = ROOT / "docs" / "contracts"
CONTRACT_INDEX = CONTRACTS_DIR / "CONTRACT_INDEX.md"
CASE_FACTS_MD = ROOT / "docs" / "CASE_FACTS.md"
COMPLETION_SIGNAL = "## Status: APPROVED_FOR_BUILD"


def index_is_approved() -> bool:
    if not CONTRACT_INDEX.exists():
        return False
    text = CONTRACT_INDEX.read_text(encoding="utf-8")
    return COMPLETION_SIGNAL in text


def approved_contracts() -> list[Path]:
    contracts: list[Path] = []
    for path in sorted(CONTRACTS_DIR.glob("*.md")):
        if path.name == "CONTRACT_INDEX.md":
            continue
        text = path.read_text(encoding="utf-8")
        if "Status: approved" in text or "`approved`" in text:
            contracts.append(path)
    return contracts


class ContractWatcher(FileSystemEventHandler):
    def __init__(self) -> None:
        self._triggered = False

    def on_modified(self, event) -> None:
        if event.is_directory or self._triggered:
            return
        path = Path(event.src_path).resolve()
        if path != CONTRACT_INDEX:
            return
        if not index_is_approved():
            return

        self._triggered = True
        run_managed_builder()


def run_managed_builder() -> None:
    if not CASE_FACTS_MD.exists():
        sys.exit("ERROR: docs/CASE_FACTS.md not found.")

    contracts = approved_contracts()
    if not contracts:
        sys.exit("ERROR: no approved module contracts found in docs/contracts/.")

    for contract in contracts:
        log.info("Launching managed_builder.py for %s", contract.name)
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "managed_builder.py"),
            "--contract",
            str(contract),
            "--case-facts",
            str(CASE_FACTS_MD),
            "--target",
            str(ROOT),
        ]
        result = subprocess.run(cmd)
        if result.returncode != 0:
            sys.exit(f"ERROR: managed_builder.py failed for {contract.name}")

    log.info("Builds finished. Run reviewer, then integrator, in Claude Code.")


def main() -> None:
    required_env = (
        "ANTHROPIC_API_KEY",
        "MANAGED_BUILDER_ENVIRONMENT_ID",
        "MANAGED_BUILDER_AGENT_ID",
        "MANAGED_BUILDER_AGENT_VERSION",
    )
    missing = [name for name in required_env if not os.environ.get(name)]
    if missing:
        sys.exit(f"ERROR: required env vars not set: {', '.join(missing)}")

    log.info("Watching %s for %r", CONTRACT_INDEX, COMPLETION_SIGNAL)
    handler = ContractWatcher()
    observer = Observer()
    observer.schedule(handler, str(CONTRACTS_DIR), recursive=False)
    observer.start()
    try:
        while True:
            import time

            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
