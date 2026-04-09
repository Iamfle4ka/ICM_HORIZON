"""
Audit Trail helper — utils/audit.py
Každý uzel pipeline volá _audit() pro zápis do immutable audit logu.
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline.state import AgentState, AuditEvent

log = logging.getLogger(__name__)


def _audit(
    state: "AgentState",
    node: str,
    action: str,
    result: str,
    metadata: dict | None = None,
    prompt: str | None = None,
    prompt_version: str | None = None,
    tokens_used: int | None = None,
) -> list["AuditEvent"]:
    """
    Přidá event do Audit Trail (append-only, immutable).

    Args:
        state:          Aktuální AgentState
        node:           Název uzlu (např. "DataExtractorAgent")
        action:         Co se děje (např. "extraction_started")
        result:         Výsledek (např. "success" | "failed" | "frozen")
        metadata:       Volitelná extra data (dict)
        prompt:         System prompt (pro AI uzly) → automaticky hashuje sha256[:12]
                        Pro DET uzly: None → prompt_hash=None v logu
        prompt_version: Verze promptu z YAML skill souboru
        tokens_used:    Počet LLM tokenů (pro AI uzly), None pro DET uzly

    Returns:
        Nový seznam AuditEvent (původní + nový event).
        Použití: state["audit_trail"] = _audit(state, ...)
    """
    # Prompt hashing — POUZE pro AI uzly
    prompt_hash: str | None = None
    if prompt is not None:
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]

    event = {
        "timestamp":      datetime.now(timezone.utc).isoformat(),
        "node":           node,
        "action":         action,
        "result":         result,
        "prompt_hash":    prompt_hash,
        "prompt_version": prompt_version,
        "tokens_used":    tokens_used,
        "metadata":       metadata or {},
    }

    log.info(
        f"[AUDIT] {node} | {action} | {result} | "
        f"hash={prompt_hash} | tokens={tokens_used}"
    )

    existing = state.get("audit_trail", []) or []
    return [*existing, event]


def compute_prompt_hash(prompt: str) -> str:
    """Vrátí sha256[:12] hash promptu. Použití: pro logy a UI."""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]


def format_audit_trail_summary(audit_trail: list) -> str:
    """
    Formátuje audit trail pro textový výstup.
    Použití: v diff reportu nebo export.
    """
    lines = []
    for i, event in enumerate(audit_trail, 1):
        ts = event.get("timestamp", "N/A")
        node = event.get("node", "N/A")
        action = event.get("action", "N/A")
        result = event.get("result", "N/A")
        ph = event.get("prompt_hash")
        ph_str = f" [hash:{ph}]" if ph else " [DET]"
        lines.append(f"{i:02d}. [{ts}] {node} | {action} → {result}{ph_str}")
    return "\n".join(lines)


if __name__ == "__main__":
    # Smoke test
    state = {"audit_trail": []}
    trail = _audit(
        state,
        node="TestNode",
        action="test_action",
        result="success",
        prompt="Test system prompt",
        prompt_version="1.0",
        tokens_used=150,
    )
    assert len(trail) == 1
    assert trail[0]["prompt_hash"] is not None
    assert len(trail[0]["prompt_hash"]) == 12

    # DET uzel — bez promptu
    state2 = {"audit_trail": trail}
    trail2 = _audit(state2, node="DetNode", action="validate", result="ok")
    assert trail2[1]["prompt_hash"] is None
    assert len(trail2) == 2

    print("OK — audit.py smoke test passed")
