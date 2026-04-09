# DETERMINISTIC
"""
Fáze 4 — Human Audit & Decision — pipeline/nodes/phase4_human_audit.py

Uzly:
  - human_review_node       ← nastaví stav AWAITING_HUMAN (DETERMINISTIC)
  - record_human_decision   ← zapíše rozhodnutí underwritera (DETERMINISTIC)

Žádný LLM — čistý Python.
4-Eyes Rule: každé Credit Memo musí schválit nebo zamítnout underwriter.
"""

import logging

from pipeline.state import ProcessStatus
from utils.audit import _audit

log = logging.getLogger(__name__)


# DETERMINISTIC
def human_review_node(state: dict) -> dict:
    """
    Připraví stav pipeline pro human review.

    Změní status na AWAITING_HUMAN a zaloguje audit event.
    UI zobrazí Credit Memo + WCR report underwriterovi.
    Pipeline čeká dokud underwriter nerozhodne.

    Čistý Python, žádný LLM.
    """
    ico = state.get("ico", "UNKNOWN")
    log.info(f"[HumanReview] Připravuji human review | ico={ico}")

    draft_memo = state.get("draft_memo", "")
    wcr_passed = state.get("wcr_passed")
    wcr_report = state.get("wcr_report", {})
    checker_verdict = state.get("checker_verdict", "unknown")
    citation_coverage = state.get("citation_coverage", 0.0)
    maker_iteration = state.get("maker_iteration", 1)

    # Sestavení review summary pro audit log
    review_summary = {
        "ico":               ico,
        "checker_verdict":   checker_verdict,
        "citation_coverage": citation_coverage,
        "wcr_passed":        wcr_passed,
        "wcr_breaches":      wcr_report.get("breaches", []),
        "maker_iteration":   maker_iteration,
        "memo_length":       len(draft_memo),
        "ew_alert_level":    _derive_ew_level(state),
    }

    log.info(
        f"[HumanReview] Awaiting human decision | ico={ico} "
        f"wcr_passed={wcr_passed} checker={checker_verdict} "
        f"coverage={citation_coverage:.2f} iteration={maker_iteration}"
    )

    audit = _audit(
        state,
        node="HumanReview",
        action="awaiting_decision",
        result="awaiting_human",
        metadata=review_summary,
    )

    return {
        **state,
        "status":      ProcessStatus.AWAITING,
        "audit_trail": audit,
    }


# DETERMINISTIC
def record_human_decision(state: dict, decision: str, comments: str = "") -> dict:
    """
    Zaznamená rozhodnutí underwritera a aktualizuje stav pipeline.

    Args:
        state:    Aktuální AgentState
        decision: "approve" | "reject" | "approve_with_conditions"
        comments: Volitelný komentář underwritera (textový diff/poznámka)

    Returns:
        Aktualizovaný state se:
        - human_decision:   str  — rozhodnutí
        - human_comments:   str  — komentář
        - underwriter_diff: str  — diff změn (pokud underwriter upravil memo)
        - status:           COMPLETED nebo FAILED
    """
    ico = state.get("ico", "UNKNOWN")
    log.info(
        f"[HumanReview] Zaznamenávám rozhodnutí | ico={ico} decision={decision!r}"
    )

    valid_decisions = {"approve", "reject", "approve_with_conditions"}
    if decision not in valid_decisions:
        log.error(
            f"[HumanReview] Neplatné rozhodnutí | ico={ico} "
            f"decision={decision!r} allowed={valid_decisions}"
        )
        audit = _audit(
            state,
            node="HumanReview",
            action="invalid_decision",
            result="error",
            metadata={"ico": ico, "decision": decision},
        )
        return {**state, "audit_trail": audit}

    # Mapování rozhodnutí na ProcessStatus
    new_status = {
        "approve":                  ProcessStatus.COMPLETED,
        "approve_with_conditions":  ProcessStatus.COMPLETED,
        "reject":                   ProcessStatus.FAILED,
    }[decision]

    # Výpočet underwriter diff (pokud komentář obsahuje změny)
    underwriter_diff = _compute_diff(
        original_memo=state.get("draft_memo", ""),
        comments=comments,
    )

    log.info(
        f"[HumanReview] Rozhodnutí zaznamenáno | ico={ico} "
        f"decision={decision} new_status={new_status}"
    )

    audit = _audit(
        state,
        node="HumanReview",
        action="decision_recorded",
        result=decision,
        metadata={
            "ico":              ico,
            "decision":         decision,
            "has_comments":     bool(comments),
            "has_diff":         bool(underwriter_diff),
            "new_status":       new_status,
        },
    )

    return {
        **state,
        "human_decision":   decision,
        "human_comments":   comments,
        "underwriter_diff": underwriter_diff,
        "status":           new_status,
        "audit_trail":      audit,
    }


# ── Privátní helpers ───────────────────────────────────────────────────────────


def _derive_ew_level(state: dict) -> str:
    """
    Odvozuje Early Warning úroveň z finančních metrik.
    Použití: pro audit log při human review.
    """
    metrics = state.get("financial_metrics", {})
    wcr_report = state.get("wcr_report", {})
    breaches = wcr_report.get("failed_rules", 0)
    dpd = metrics.get("dpd_current", 0)

    if breaches >= 3 or dpd > 30:
        return "RED"
    if breaches >= 1 or dpd > 0:
        return "AMBER"
    return "GREEN"


def _compute_diff(original_memo: str, comments: str) -> str:
    """
    Jednoduchý diff — vrací komentář pokud je neprázdný.
    V produkci by to byl skutečný text diff, ale pro demo
    stačí zaznamenat komentář underwritera jako diff.
    """
    if not comments:
        return ""
    return f"[Underwriter poznámky — {len(comments)} znaků]:\n{comments}"


if __name__ == "__main__":
    # Smoke test
    from pipeline.state import make_initial_state

    state = make_initial_state("27082440", "REQ-SMOKE-005")
    state["draft_memo"] = "# Credit Memo — test"
    state["wcr_passed"] = True
    state["wcr_report"] = {"breaches": [], "failed_rules": 0, "passed_rules": 5}
    state["checker_verdict"] = "pass"
    state["citation_coverage"] = 0.93
    state["maker_iteration"] = 1
    state["financial_metrics"] = {"leverage_ratio": 3.8, "dscr": 1.45, "dpd_current": 0}

    # Test human_review_node
    state = human_review_node(state)
    assert state["status"] == ProcessStatus.AWAITING
    print(f"  Status: {state['status']}")

    # Test approve
    state = record_human_decision(state, "approve", "Vše v pořádku.")
    assert state["status"] == ProcessStatus.COMPLETED
    assert state["human_decision"] == "approve"
    print(f"  Decision: {state['human_decision']} → status={state['status']}")

    # Test reject
    state2 = make_initial_state("49551895", "REQ-SMOKE-006")
    state2["draft_memo"] = "test"
    state2["financial_metrics"] = {"dpd_current": 45}
    state2["wcr_report"] = {"breaches": ["x", "y", "z"], "failed_rules": 3}
    state2 = human_review_node(state2)
    state2 = record_human_decision(state2, "reject", "Příliš vysoké DPD.")
    assert state2["status"] == ProcessStatus.FAILED
    print(f"  Reject: {state2['human_decision']} → status={state2['status']}")

    print("OK — phase4_human_audit.py smoke test passed")
