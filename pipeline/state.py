"""
AgentState + všechny datové modely — pipeline/state.py
Datové modely pro DP1 Credit Memo pipeline.
"""

from __future__ import annotations

from enum import Enum


# ── Enums ─────────────────────────────────────────────────────────────────────


class ProcessStatus(str, Enum):
    RUNNING   = "running"
    FROZEN    = "frozen"           # API failure → Process Freeze, NE T-1 fallback
    ESCALATED = "escalated"        # max iterací nebo kritická chyba
    AWAITING  = "awaiting_human"
    COMPLETED = "completed"
    FAILED    = "failed"


# ── Datové modely ─────────────────────────────────────────────────────────────


class AuditEvent(dict):
    """
    Immutable audit event. Rozšiřuje dict pro JSON serializaci.
    Klíče: timestamp, node, action, result, prompt_hash,
            prompt_version, tokens_used, metadata.
    """
    pass


class FinancialMetrics(dict):
    """
    Finanční metriky klienta.
    Raw inputs + deterministicky vypočtené koeficienty.
    LLM se NIKDY nedotýká výpočtů.
    """
    pass


class CaseView(dict):
    """
    Kompletní pohled na klienta sestavený v Phase 2.
    Každé pole má přiřazený source_id pro citace v memu.
    """
    pass


class ExtractionResult(dict):
    """
    Výsledek Phase 1 — data_extractor_agent.
    Obsahuje raw extrahovaná data + confidence_score.
    """
    pass


class AgentState(dict):
    """
    Centrální stav LangGraph pipeline.
    Všechny uzly čtou a zapisují do tohoto stavu.

    Immutable pravidlo: audit_trail se POUZE rozrůstá (append-only).
    GDPR: citlivá klientská data jsou vyčištěna po schválení.
    """
    pass


# ── Výchozí hodnoty ───────────────────────────────────────────────────────────


def make_initial_state(ico: str, request_id: str) -> AgentState:
    """
    Vytvoří výchozí AgentState pro nový request.
    """
    from datetime import datetime, timezone
    return AgentState(
        # Identifikace
        ico=ico,
        request_id=request_id,
        created_at=datetime.now(timezone.utc).isoformat(),

        # Fáze 1
        extraction_result=None,
        extraction_attempts=0,
        fallback_reason=None,

        # Fáze 2
        case_view=None,
        financial_metrics=None,

        # Fáze 3 — Maker-Checker Loop
        draft_memo=None,
        citation_coverage=0.0,
        hallucination_report=[],
        maker_iteration=0,
        checker_verdict=None,

        # WCR (deterministický)
        wcr_passed=None,
        wcr_report=None,

        # Finální
        status=ProcessStatus.RUNNING,
        escalation_reason=None,
        human_decision=None,
        human_comments=None,
        underwriter_diff=None,

        # Audit Trail — immutable append
        audit_trail=[],
        messages=[],
    )


if __name__ == "__main__":
    # Smoke test
    state = make_initial_state("27082440", "REQ-001")
    assert state["ico"] == "27082440"
    assert state["status"] == ProcessStatus.RUNNING
    assert state["audit_trail"] == []
    print("OK — state.py smoke test passed")
