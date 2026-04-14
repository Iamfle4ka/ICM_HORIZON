# AI + DETERMINISTIC
"""
Fáze 3 — Maker-Checker Loop — pipeline/nodes/phase3_maker_checker.py

Uzly:
  - memo_preparation_agent   ← LLM píše Credit Memo (AI, maker_skill.yaml)
  - quality_control_checker  ← LLM kontroluje citace/halucinace (AI, checker_skill.yaml)
  - policy_rules_engine      ← deterministická WCR kontrola (DETERMINISTIC)

Garantované guardy:
  - MAX_MAKER_ITERATIONS = 3  (loop guard)
  - MIN_CITATION_COVERAGE = 0.90
  - API failure → Process Freeze
"""

import json
import logging
import re
import time

from pipeline.state import ProcessStatus
from skills import registry
from utils.audit import _audit
from utils.wcr_rules import (
    API_RETRY_COUNT,
    API_RETRY_DELAY_SEC,
    MAX_MAKER_ITERATIONS,
    MIN_CITATION_COVERAGE,
)

log = logging.getLogger(__name__)


# AI
def memo_preparation_agent(state: dict) -> dict:
    """
    Napíše Credit Memo na základě předem vypočtených metrik (maker_skill.yaml).

    ABSOLUTNÍ PRAVIDLO: agent NIKDY sám nepočítá matematiku —
    všechny metriky jsou předány z financial_metrics (vypočteny deterministicky).

    Re-iterace: pokud checker_verdict == "fail" a maker_iteration < MAX,
    opraví memo na základě hallucination_report.

    Vstupy ze state:
        case_view, financial_metrics, maker_iteration,
        checker_verdict, hallucination_report, draft_memo (pro re-iterace)

    Výstupy do state:
        draft_memo, maker_iteration
    """
    ico = state.get("ico", "UNKNOWN")
    iteration = state.get("maker_iteration", 0) + 1
    log.info(
        f"[MemoPreparationAgent] Zahajuji tvorbu mema | ico={ico} iteration={iteration}"
    )

    # Loop guard
    if iteration > MAX_MAKER_ITERATIONS:
        log.warning(
            f"[MemoPreparationAgent] Max iterací dosažen | ico={ico} max={MAX_MAKER_ITERATIONS}"
        )
        audit = _audit(
            state,
            node="MemoPreparationAgent",
            action="max_iterations_reached",
            result="escalated",
            metadata={"ico": ico, "iteration": iteration, "max": MAX_MAKER_ITERATIONS},
        )
        return {
            **state,
            "status":            ProcessStatus.ESCALATED,
            "escalation_reason": f"Maker agent překročil {MAX_MAKER_ITERATIONS} iterací",
            "maker_iteration":   iteration,
            "audit_trail":       audit,
        }

    skill = registry.get("maker_skill")
    prompt = skill["prompt"]
    skill_version = skill["version"]

    case_view = state.get("case_view", {})
    metrics = state.get("financial_metrics", {})
    data_sources = case_view.get("data_sources", {})

    # Sestavení user message
    re_iter_section = ""
    if iteration > 1:
        hallucinations = state.get("hallucination_report", [])
        prev_memo = state.get("draft_memo", "")
        re_iter_section = (
            f"\n\nRE-ITERACE {iteration}: Oprav POUZE tyto problémy:\n"
            + "\n".join(f"- {h}" for h in hallucinations)
            + f"\n\nPŘEDCHOZÍ MEMO (zachovej co je správně):\n{prev_memo}"
        )

    user_message = (
        f"IČO: {case_view.get('ico', ico)}\n"
        f"Společnost: {case_view.get('company_name', '')}\n\n"
        f"PŘEDEM VYPOČTENÉ METRIKY (neměň, nepočítej):\n"
        f"- Leverage Ratio: {metrics.get('leverage_ratio', 'N/A')}x\n"
        f"- DSCR: {metrics.get('dscr', 'N/A')}\n"
        f"- Current Ratio: {metrics.get('current_ratio', 'N/A')}\n"
        f"- Využití limitu: {metrics.get('utilisation_pct', 'N/A')} %\n"
        f"- DPD: {metrics.get('dpd_current', 'N/A')} dní\n"
        f"- EBITDA: {_fmt_m(metrics.get('ebitda'))} M CZK\n"
        f"- Revenue: {_fmt_m(metrics.get('revenue'))} M CZK\n"
        f"- Net Debt: {_fmt_m(metrics.get('net_debt'))} M CZK\n\n"
        f"DATA_SOURCES (povolené source_id pro citace):\n"
        + "\n".join(f"- {k}: {v}" for k, v in data_sources.items())
        + f"\n\nDOPLŇUJÍCÍ DATA:\n"
        f"- Limit: {_fmt_m(case_view.get('credit_limit'))} M CZK\n"
        f"- Čerpání: {_fmt_m(case_view.get('current_utilisation'))} M CZK\n"
        f"- Covenant: {metrics.get('covenant_status', case_view.get('covenant_status', 'N/A'))}\n"
        f"- CMP monitoring: {metrics.get('cmp_monitored', False)}\n"
        f"- Restrukturalizace: {metrics.get('is_restructured', False)}\n"
        f"- Délka vztahu: {metrics.get('relationship_years', 'N/A')} let\n"
        f"- Průměrný obrat: {_fmt_m(case_view.get('silver_metrics', {}).get('avg_monthly_credit_turnover'))} M CZK/měsíc\n"
        f"- Internal rating: {metrics.get('internal_rating', 'N/A')}\n"
        f"- wcr_partial: {metrics.get('wcr_partial', False)} (True = Leverage/DSCR/Current Ratio chybí)\n"
        + re_iter_section
    )

    # Claude API s retry
    last_error: str | None = None
    for attempt in range(1, API_RETRY_COUNT + 1):
        log.info(
            f"[MemoPreparationAgent] API volání pokus {attempt}/{API_RETRY_COUNT} | "
            f"ico={ico} iteration={iteration}"
        )
        try:
            from utils.llm_factory import get_llm

            api_client  = get_llm()
            response    = api_client.complete(
                system=prompt,
                user_message=user_message,
                max_tokens=4096,
            )
            draft_memo  = response.text
            tokens_used = response.tokens_used

            log.info(
                f"[MemoPreparationAgent] Memo napsáno | ico={ico} "
                f"iteration={iteration} tokens={tokens_used} len={len(draft_memo)}"
            )
            audit = _audit(
                state,
                node="MemoPreparationAgent",
                action="memo_drafted",
                result="success",
                prompt=prompt,
                prompt_version=skill_version,
                tokens_used=tokens_used,
                metadata={
                    "ico":        ico,
                    "iteration":  iteration,
                    "memo_length": len(draft_memo),
                },
            )
            return {
                **state,
                "draft_memo":      draft_memo,
                "maker_iteration": iteration,
                "audit_trail":     audit,
            }

        except Exception as exc:
            last_error = str(exc)
            log.warning(
                f"[MemoPreparationAgent] API chyba pokus {attempt}/{API_RETRY_COUNT} | "
                f"ico={ico} error={last_error}"
            )
            if attempt < API_RETRY_COUNT:
                time.sleep(API_RETRY_DELAY_SEC)

    # Process Freeze
    log.error(
        f"[MemoPreparationAgent] Process Freeze | ico={ico} last_error={last_error}"
    )
    audit = _audit(
        state,
        node="MemoPreparationAgent",
        action="memo_failed",
        result="process_freeze",
        prompt=prompt,
        prompt_version=skill_version,
        metadata={"ico": ico, "iteration": iteration, "last_error": last_error},
    )
    return {
        **state,
        "status":          ProcessStatus.FROZEN,
        "fallback_reason": f"Maker API selhala po {API_RETRY_COUNT} pokusech: {last_error}",
        "maker_iteration": iteration,
        "audit_trail":     audit,
    }


# AI
def quality_control_checker(state: dict) -> dict:
    """
    Kontroluje citace a halucinace v Credit Memu (checker_skill.yaml).

    Zodpovědnost checker agenta:
    - Citation coverage >= 90 %
    - Validita source_id (pouze povolené ze data_sources)
    - Halucinace (tvrzení bez podkladu)

    MIMO zodpovědnost checkeru (řeší jiné uzly):
    - WCR limity (policy_rules_engine — deterministický)
    - Matematika (credit_analysis_service — deterministický)
    """
    ico = state.get("ico", "UNKNOWN")
    iteration = state.get("maker_iteration", 1)
    log.info(
        f"[QualityControlChecker] Zahajuji quality check | ico={ico} iteration={iteration}"
    )

    draft_memo = state.get("draft_memo", "")
    if not draft_memo:
        log.error(f"[QualityControlChecker] Chybí draft_memo | ico={ico}")
        audit = _audit(
            state,
            node="QualityControlChecker",
            action="check_failed",
            result="missing_draft_memo",
            metadata={"ico": ico},
        )
        return {**state, "checker_verdict": "fail", "audit_trail": audit}

    case_view = state.get("case_view", {})
    data_sources = case_view.get("data_sources", {})

    skill = registry.get("checker_skill")
    prompt = skill["prompt"]
    skill_version = skill["version"]

    user_message = (
        f"POVOLENÉ SOURCE_ID (pouze tyto jsou platné):\n"
        + "\n".join(f"- {k}: {v}" for k, v in data_sources.items())
        + f"\n\nCREDIT MEMO K OVĚŘENÍ:\n{draft_memo}"
    )

    last_error: str | None = None
    for attempt in range(1, API_RETRY_COUNT + 1):
        log.info(
            f"[QualityControlChecker] API volání pokus {attempt}/{API_RETRY_COUNT} | "
            f"ico={ico}"
        )
        try:
            from utils.llm_factory import get_llm

            api_client  = get_llm()
            response    = api_client.complete(
                system=prompt,
                user_message=user_message,
                max_tokens=1024,
            )
            raw_text    = response.text
            tokens_used = response.tokens_used

            check_result = json.loads(_extract_json(raw_text))

            coverage = float(check_result.get("coverage_pct", 0.0))
            hallucinations = check_result.get("hallucinations", [])
            invalid_sources = check_result.get("invalid_source_ids", [])
            verdict = check_result.get("verdict", "fail")

            log.info(
                f"[QualityControlChecker] Check hotov | ico={ico} "
                f"coverage={coverage:.2f} hallucinations={len(hallucinations)} "
                f"verdict={verdict}"
            )

            # Sestavení hallucination_report pro Maker re-iteraci
            hallucination_report = []
            for h in hallucinations:
                hallucination_report.append(f"Halucinace: {h}")
            for s in invalid_sources:
                hallucination_report.append(f"Neplatný source_id: '{s}'")
            if coverage < MIN_CITATION_COVERAGE:
                hallucination_report.append(
                    f"Nízká citation coverage: {coverage:.1%} < {MIN_CITATION_COVERAGE:.0%}"
                )

            audit = _audit(
                state,
                node="QualityControlChecker",
                action="quality_check",
                result=verdict,
                prompt=prompt,
                prompt_version=skill_version,
                tokens_used=tokens_used,
                metadata={
                    "ico":                 ico,
                    "iteration":           iteration,
                    "coverage_pct":        coverage,
                    "hallucinations_count": len(hallucinations),
                    "invalid_sources":     invalid_sources,
                    "verdict":             verdict,
                },
            )
            return {
                **state,
                "citation_coverage":   coverage,
                "hallucination_report": hallucination_report,
                "checker_verdict":     verdict,
                "audit_trail":         audit,
            }

        except Exception as exc:
            last_error = str(exc)
            log.warning(
                f"[QualityControlChecker] API chyba pokus {attempt}/{API_RETRY_COUNT} | "
                f"ico={ico} error={last_error}"
            )
            if attempt < API_RETRY_COUNT:
                time.sleep(API_RETRY_DELAY_SEC)

    # Process Freeze
    log.error(
        f"[QualityControlChecker] Process Freeze | ico={ico} last_error={last_error}"
    )
    audit = _audit(
        state,
        node="QualityControlChecker",
        action="check_failed",
        result="process_freeze",
        prompt=prompt,
        prompt_version=skill_version,
        metadata={"ico": ico, "last_error": last_error},
    )
    return {
        **state,
        "status":          ProcessStatus.FROZEN,
        "fallback_reason": f"Checker API selhala po {API_RETRY_COUNT} pokusech: {last_error}",
        "checker_verdict": "fail",
        "audit_trail":     audit,
    }


# DETERMINISTIC
def policy_rules_engine(state: dict) -> dict:
    """
    Deterministická WCR kontrola — build_wcr_report.

    Používá předem vypočtené metriky z financial_metrics.
    ŽÁDNÝ LLM — čistý Python.

    Výstupy do state:
        wcr_passed:  bool
        wcr_report:  dict  — detailní report per pravidlo
    """
    ico = state.get("ico", "UNKNOWN")
    log.info(f"[PolicyRulesEngine] Zahajuji WCR kontrolu | ico={ico}")

    metrics = state.get("financial_metrics")
    if not metrics:
        log.error(f"[PolicyRulesEngine] Chybí financial_metrics | ico={ico}")
        audit = _audit(
            state,
            node="PolicyRulesEngine",
            action="wcr_check_failed",
            result="missing_metrics",
            metadata={"ico": ico},
        )
        return {**state, "audit_trail": audit}

    # DETERMINISTIC — partial WCR (uses pre-computed results from CreditAnalysisService)
    # metrics.wcr_breaches already handles None correctly (from phase2)
    breaches = list(metrics.get("wcr_breaches", []))
    wcr_skipped = list(metrics.get("wcr_skipped", []))
    wcr_partial = bool(metrics.get("wcr_partial", False))

    utilisation_pct = float(
        metrics.get("credit_limit_utilization_pct")
        or metrics.get("utilisation_pct")
        or 0.0
    )
    dpd_current    = int(metrics.get("dpd_current", 0))
    leverage_ratio = metrics.get("leverage_ratio")   # None = wyžaduje CRIBIS
    dscr           = metrics.get("dscr")             # None = vyžaduje CRIBIS
    current_ratio  = metrics.get("current_ratio")    # None = vyžaduje CRIBIS

    from datetime import datetime, timezone
    from utils.wcr_rules import WCR_LIMITS
    checked = 2 + (3 - len(wcr_skipped))
    completeness = f"{checked}/5 pravidel zkontrolováno"

    rules_detail = {
        "utilisation": {
            "value": round(utilisation_pct, 1),
            "limit": WCR_LIMITS["max_utilisation_pct"],
            "passed": utilisation_pct <= WCR_LIMITS["max_utilisation_pct"],
            "source": "credit_history", "unit": "%", "skipped": False,
        },
        "dpd": {
            "value": dpd_current,
            "limit": WCR_LIMITS["max_dpd_days"],
            "passed": dpd_current <= WCR_LIMITS["max_dpd_days"],
            "source": "credit_history", "unit": " dní", "skipped": False,
        },
        "leverage": (
            {"value": leverage_ratio, "limit": WCR_LIMITS["max_leverage_ratio"],
             "passed": leverage_ratio <= WCR_LIMITS["max_leverage_ratio"],
             "source": "cribis_external", "unit": "x", "skipped": False}
            if leverage_ratio is not None else
            {"value": None, "limit": WCR_LIMITS["max_leverage_ratio"],
             "passed": None, "note": "Vyžaduje CRIBIS", "skipped": True, "unit": "x"}
        ),
        "dscr": (
            {"value": dscr, "limit": WCR_LIMITS["min_dscr"],
             "passed": dscr >= WCR_LIMITS["min_dscr"],
             "source": "cribis_external", "unit": "", "skipped": False}
            if dscr is not None else
            {"value": None, "limit": WCR_LIMITS["min_dscr"],
             "passed": None, "note": "Vyžaduje CRIBIS", "skipped": True, "unit": ""}
        ),
        "current_ratio": (
            {"value": current_ratio, "limit": WCR_LIMITS["min_current_ratio"],
             "passed": current_ratio >= WCR_LIMITS["min_current_ratio"],
             "source": "cribis_external", "unit": "", "skipped": False}
            if current_ratio is not None else
            {"value": None, "limit": WCR_LIMITS["min_current_ratio"],
             "passed": None, "note": "Vyžaduje CRIBIS", "skipped": True, "unit": ""}
        ),
    }
    passed_rules = sum(1 for r in rules_detail.values() if r.get("passed") is True)
    failed_rules = sum(1 for r in rules_detail.values() if r.get("passed") is False)

    wcr_report = {
        "rules":            list(rules_detail.values()),
        "rules_detail":     rules_detail,
        "total_rules":      5,
        "passed_rules":     passed_rules,
        "failed_rules":     failed_rules,
        "breaches":         breaches,
        "skipped_rules":    wcr_skipped,
        "overall_passed":   len(breaches) == 0,
        "wcr_partial":      wcr_partial,
        "data_completeness": completeness,
        "checked_at":       datetime.now(timezone.utc).isoformat(),
    }
    wcr_passed = not breaches
    log.info(
        f"[PolicyRulesEngine] WCR check hotov | ico={ico} "
        f"passed={wcr_passed} breaches={len(breaches)}"
    )

    audit = _audit(
        state,
        node="PolicyRulesEngine",
        action="wcr_check",
        result="passed" if wcr_passed else f"{len(breaches)}_breaches",
        metadata={
            "ico":         ico,
            "wcr_passed":  wcr_passed,
            "breaches":    breaches,
            "rules_passed": wcr_report["passed_rules"],
            "rules_failed": wcr_report["failed_rules"],
        },
    )
    return {
        **state,
        "wcr_passed":  wcr_passed,
        "wcr_report":  wcr_report,
        "audit_trail": audit,
    }


# ── Privátní helpers ───────────────────────────────────────────────────────────


def _extract_json(text: str) -> str:
    """Extrahuje JSON ze surové LLM odpovědi."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return m.group(1)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        return m.group(0)
    return text


def _fmt_m(value) -> str:
    """Formátuje hodnotu v CZK na M CZK."""
    if value is None:
        return "N/A"
    try:
        return f"{float(value) / 1_000_000:.1f}"
    except (TypeError, ValueError):
        return str(value)


if __name__ == "__main__":
    # Smoke test — policy_rules_engine (DETERMINISTIC, bez API)
    from pipeline.state import make_initial_state

    state = make_initial_state("27082440", "REQ-SMOKE-003")
    state["financial_metrics"] = {
        "leverage_ratio":  3.8,
        "dscr":            1.45,
        "current_ratio":   1.55,
        "utilisation_pct": 65.0,
        "dpd_current":     0,
        "ebitda":          180_000_000.0,
        "net_debt":        684_000_000.0,
        "revenue":         1_200_000_000.0,
    }

    state = policy_rules_engine(state)
    assert state["wcr_passed"] is True, f"Expected pass, got: {state.get('wcr_report')}"
    assert state["wcr_report"]["failed_rules"] == 0
    print(f"  WCR passed: {state['wcr_passed']}")
    print(f"  Rules passed: {state['wcr_report']['passed_rules']}/5")

    # Test s breaches (Textil Liberec)
    state2 = make_initial_state("49551895", "REQ-SMOKE-004")
    state2["financial_metrics"] = {
        "leverage_ratio":  5.8,
        "dscr":            0.95,
        "current_ratio":   0.74,
        "utilisation_pct": 94.7,
        "dpd_current":     45,
    }
    state2 = policy_rules_engine(state2)
    assert state2["wcr_passed"] is False
    assert state2["wcr_report"]["failed_rules"] >= 4
    print(f"  Breaches: {state2['wcr_report']['failed_rules']} (expected >= 4)")

    print("OK — phase3_maker_checker.py smoke test passed")
