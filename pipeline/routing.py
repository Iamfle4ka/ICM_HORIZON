# DETERMINISTIC
"""
Pipeline Routing — pipeline/routing.py
Podmíněné hrany LangGraph grafu.
ŽÁDNÝ LLM — čistý Python.
"""

import logging

from pipeline.state import ProcessStatus
from utils.wcr_rules import MAX_MAKER_ITERATIONS, MIN_CITATION_COVERAGE

log = logging.getLogger(__name__)


# DETERMINISTIC
def route_after_extraction(state: dict) -> str:
    """
    Po extraction_validator → rozhoduje, kam jít dál.

    Returns:
        "freeze"           — API selhala nebo nízká confidence
        "continue_phase2"  — extrakce OK
    """
    ico = state.get("ico", "UNKNOWN")
    status = state.get("status")

    if status == ProcessStatus.FROZEN:
        log.info(f"[Router] route_after_extraction → freeze | ico={ico} reason={state.get('fallback_reason')}")
        return "freeze"

    log.info(f"[Router] route_after_extraction → continue_phase2 | ico={ico}")
    return "continue_phase2"


# DETERMINISTIC
def route_after_checker(state: dict) -> str:
    """
    Po quality_control_checker → rozhoduje, kam jít dál.

    Logika:
    - Process Freeze: status == FROZEN
    - Max iterace dosaženy: status == ESCALATED
    - Checker pass: → policy_rules_engine
    - Checker fail + iterace zbývají: → memo_preparation_agent (re-iterace)

    Returns:
        "freeze"          — API selhala
        "escalate"        — max iterací dosaženo
        "policy_check"    — checker pass → WCR check
        "retry_maker"     — checker fail, re-iterace
    """
    ico = state.get("ico", "UNKNOWN")
    status = state.get("status")
    checker_verdict = state.get("checker_verdict", "fail")
    maker_iteration = state.get("maker_iteration", 1)
    citation_coverage = state.get("citation_coverage", 0.0)
    hallucination_report = state.get("hallucination_report", [])

    if status == ProcessStatus.FROZEN:
        log.info(f"[Router] route_after_checker → freeze | ico={ico}")
        return "freeze"

    if status == ProcessStatus.ESCALATED:
        log.info(f"[Router] route_after_checker → escalate | ico={ico}")
        return "escalate"

    if checker_verdict == "pass" and citation_coverage >= MIN_CITATION_COVERAGE and not hallucination_report:
        log.info(
            f"[Router] route_after_checker → policy_check | ico={ico} "
            f"coverage={citation_coverage:.2f}"
        )
        return "policy_check"

    # Checker fail — ještě zbývají iterace?
    if maker_iteration < MAX_MAKER_ITERATIONS:
        log.info(
            f"[Router] route_after_checker → retry_maker | ico={ico} "
            f"iteration={maker_iteration}/{MAX_MAKER_ITERATIONS} "
            f"verdict={checker_verdict} coverage={citation_coverage:.2f}"
        )
        return "retry_maker"

    # Max iterace — eskalace
    log.warning(
        f"[Router] route_after_checker → escalate (max iterations) | ico={ico} "
        f"iteration={maker_iteration}"
    )
    return "escalate"


# DETERMINISTIC
def route_after_policy(state: dict) -> str:
    """
    Po policy_rules_engine → vždy jde na human review.
    WCR breaches jsou informace pro underwritera, NE blokátor.

    Returns:
        "human_review"  — vždy (WCR výsledek je součástí review materiálů)
    """
    ico = state.get("ico", "UNKNOWN")
    wcr_passed = state.get("wcr_passed", True)
    breaches = state.get("wcr_report", {}).get("breaches", [])

    log.info(
        f"[Router] route_after_policy → human_review | ico={ico} "
        f"wcr_passed={wcr_passed} breaches={len(breaches)}"
    )
    return "human_review"


# DETERMINISTIC
def route_after_human_decision(state: dict) -> str:
    """
    Po record_human_decision → finální routing.

    Returns:
        "completed"   — schváleno (approve / approve_with_conditions)
        "rejected"    — zamítnuto (reject)
    """
    ico = state.get("ico", "UNKNOWN")
    decision = state.get("human_decision", "")
    status = state.get("status")

    if status == ProcessStatus.COMPLETED:
        log.info(f"[Router] route_after_human_decision → completed | ico={ico} decision={decision}")
        return "completed"

    log.info(f"[Router] route_after_human_decision → rejected | ico={ico} decision={decision}")
    return "rejected"


if __name__ == "__main__":
    # Smoke test
    from pipeline.state import ProcessStatus, make_initial_state

    # route_after_extraction — freeze
    s = make_initial_state("X", "R1")
    s["status"] = ProcessStatus.FROZEN
    assert route_after_extraction(s) == "freeze"

    # route_after_extraction — continue
    s2 = make_initial_state("X", "R2")
    assert route_after_extraction(s2) == "continue_phase2"

    # route_after_checker — pass
    s3 = make_initial_state("X", "R3")
    s3["checker_verdict"] = "pass"
    s3["citation_coverage"] = 0.95
    s3["hallucination_report"] = []
    s3["maker_iteration"] = 1
    assert route_after_checker(s3) == "policy_check"

    # route_after_checker — fail, retry
    s4 = make_initial_state("X", "R4")
    s4["checker_verdict"] = "fail"
    s4["citation_coverage"] = 0.70
    s4["hallucination_report"] = ["chyba 1"]
    s4["maker_iteration"] = 1
    assert route_after_checker(s4) == "retry_maker"

    # route_after_checker — fail, max iterations
    s5 = make_initial_state("X", "R5")
    s5["checker_verdict"] = "fail"
    s5["citation_coverage"] = 0.70
    s5["hallucination_report"] = ["chyba"]
    s5["maker_iteration"] = MAX_MAKER_ITERATIONS
    assert route_after_checker(s5) == "escalate"

    # route_after_policy
    s6 = make_initial_state("X", "R6")
    s6["wcr_passed"] = True
    s6["wcr_report"] = {"breaches": []}
    assert route_after_policy(s6) == "human_review"

    print("OK — routing.py smoke test passed")
