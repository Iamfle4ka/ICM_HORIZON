"""
Human Review & Decision — ui/page_human_review.py
Underwriter 4-Eyes Rule: zobrazí memo, WCR status a umožní rozhodnutí.
"""

import streamlit as st

from ui.styles import CITI_BLUE, fmt_pct, highlight_citations, wcr_icon
from utils.mock_data import get_mock_agent_result, get_portfolio


def render_human_review_page() -> None:
    """Renderuje Human Review stránku pro underwritera."""

    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,{CITI_BLUE} 0%,#0066CC 100%);
             color:white;padding:1.2rem 1.5rem;border-radius:10px;margin-bottom:1rem">
            <h2 style="margin:0;font-size:1.4rem">👁️ Human Review — 4-Eyes Rule</h2>
            <p style="margin:0.2rem 0 0;font-size:0.85rem;opacity:0.85">
                Underwriter review · Každé memo musí být schváleno nebo zamítnuto
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Výběr klienta k review
    portfolio = get_portfolio()
    ico_options = [f"{c['ico']} — {c['company_name']}" for c in portfolio]
    ico_map = {f"{c['ico']} — {c['company_name']}": c["ico"] for c in portfolio}

    preselected = st.session_state.get("selected_ico", "")
    default_idx = 0
    if preselected:
        matching = [i for i, opt in enumerate(ico_options) if opt.startswith(preselected)]
        if matching:
            default_idx = matching[0]

    selected_label = st.selectbox(
        "Vyberte klienta k review",
        options=ico_options,
        index=default_idx,
        key="review_ico_select",
    )
    ico = ico_map[selected_label]

    # Načtení výsledku pipeline
    result_key = f"pipeline_result_{ico}"
    result = st.session_state.get(result_key)

    if result is None:
        if st.button("📥 Načíst demo výsledek pipeline", key="load_demo_review"):
            result = get_mock_agent_result(ico)
            st.session_state[result_key] = result
            st.rerun()
        else:
            st.info("Pipeline nebyla spuštěna. Spusťte ji na stránce 'Credit Memo' nebo načtěte demo výsledek.")
            return

    _render_review_panel(result, ico)


def _render_review_panel(result: dict, ico: str) -> None:
    """Renderuje review panel s memem a rozhodovacími tlačítky."""

    company = result.get("company_name", result.get("case_view", {}).get("company_name", ico))
    decision_key = f"decision_{ico}"
    existing_decision = st.session_state.get(decision_key)

    # ── Review Summary ─────────────────────────────────────────────────────────
    wcr_passed = result.get("wcr_passed", True)
    checker_verdict = result.get("checker_verdict", "N/A")
    coverage = result.get("citation_coverage", 0.0)
    breaches = result.get("wcr_report", {}).get("breaches", [])

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Společnost", company[:20] + "..." if len(company) > 20 else company)
    col2.metric("WCR Status", "✅ PASS" if wcr_passed else f"❌ {len(breaches)} breach")
    col3.metric("Checker", checker_verdict.upper())
    col4.metric("Citation Coverage", fmt_pct(coverage * 100))

    st.markdown("---")

    # ── Memo & WCR přehled ─────────────────────────────────────────────────────
    tab_memo, tab_wcr = st.tabs(["📄 Credit Memo", "🔒 WCR Report"])

    with tab_memo:
        draft_memo = result.get("draft_memo", "")
        if draft_memo:
            html_memo = highlight_citations(draft_memo.replace("\n", "<br>"))
            st.markdown(
                f"<div style='background:white;border:1px solid #E5E7EB;border-radius:10px;"
                f"padding:1.5rem 2rem;max-height:450px;overflow-y:auto;line-height:1.7'>"
                f"{html_memo}</div>",
                unsafe_allow_html=True,
            )
        else:
            st.warning("Memo není k dispozici.")

    with tab_wcr:
        wcr_report = result.get("wcr_report", {})
        if wcr_report:
            for rule in wcr_report.get("rules", []):
                passed = rule.get("passed", True)
                icon = wcr_icon(passed)
                bg = "#F0FDF4" if passed else "#FEF2F2"
                unit = rule.get("unit", "")
                st.markdown(
                    f"<div style='background:{bg};padding:0.5rem 0.8rem;border-radius:6px;margin:0.3rem 0'>"
                    f"{icon} <strong>{rule.get('description','')}</strong> — "
                    f"Hodnota: <strong>{rule.get('value','N/A')}{unit}</strong> "
                    f"(Limit: {rule.get('limit','N/A')}{unit})</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.info("WCR report není dostupný.")

    st.markdown("---")

    # ── Rozhodovací panel ──────────────────────────────────────────────────────
    if existing_decision:
        dec_color = {"approve": "#16A34A", "reject": "#DC2626", "approve_with_conditions": "#D97706"}
        dec_label = {
            "approve": "✅ SCHVÁLENO",
            "reject": "❌ ZAMÍTNUTO",
            "approve_with_conditions": "⚠️ PODMÍNEČNĚ SCHVÁLENO",
        }
        color = dec_color.get(existing_decision["decision"], "#6B7280")
        label = dec_label.get(existing_decision["decision"], existing_decision["decision"])
        st.markdown(
            f"<div style='background:{color};color:white;padding:1rem 1.5rem;"
            f"border-radius:10px;font-weight:700;font-size:1.1rem'>"
            f"{label}</div>",
            unsafe_allow_html=True,
        )
        if existing_decision.get("comments"):
            st.markdown(f"**Komentář underwritera:** {existing_decision['comments']}")

        if st.button("🔄 Změnit rozhodnutí", key=f"change_dec_{ico}"):
            del st.session_state[decision_key]
            st.rerun()
        return

    st.markdown("#### 📋 Rozhodnutí underwritera")
    comments = st.text_area(
        "Komentář / odůvodnění (volitelné)",
        placeholder="Např.: Doporučuji schválit s podmínkou pravidelného reportingu...",
        key=f"comments_{ico}",
        height=100,
    )

    col_approve, col_conditions, col_reject = st.columns(3)

    with col_approve:
        if st.button("✅ Schválit", key=f"approve_{ico}", type="primary", use_container_width=True):
            _record_decision(ico, "approve", comments)

    with col_conditions:
        if st.button("⚠️ Podmínečně schválit", key=f"cond_{ico}", use_container_width=True):
            _record_decision(ico, "approve_with_conditions", comments)

    with col_reject:
        if st.button("❌ Zamítnout", key=f"reject_{ico}", use_container_width=True):
            _record_decision(ico, "reject", comments)

    if not wcr_passed:
        st.warning(
            f"⚠️ Upozornění: Klient má {len(breaches)} WCR porušení. "
            "Zkontrolujte WCR Report před rozhodnutím."
        )


def _record_decision(ico: str, decision: str, comments: str) -> None:
    """Zaznamená rozhodnutí do session state a aktualizuje pipeline state."""
    from pipeline.nodes.phase4_human_audit import record_human_decision

    result_key = f"pipeline_result_{ico}"
    decision_key = f"decision_{ico}"

    result = st.session_state.get(result_key, {})
    updated = record_human_decision(result, decision, comments)
    st.session_state[result_key] = updated
    st.session_state[decision_key] = {"decision": decision, "comments": comments}

    # Aktualizace audit trail stránky
    st.session_state[f"audit_ico"] = ico
    st.rerun()
