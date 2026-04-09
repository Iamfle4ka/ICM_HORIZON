"""
Credit Memo Generation — ui/page_credit_memo.py
Spustí pipeline a zobrazí výsledek: Credit Memo + WCR report + Checker výsledek.
"""

import streamlit as st

from ui.styles import (
    CITI_BLUE,
    fmt_czk,
    fmt_pct,
    highlight_citations,
    wcr_icon,
)
from utils.mock_data import get_client, get_mock_agent_result


def render_credit_memo_page() -> None:
    """Renderuje Credit Memo stránku pro vybrané IČO."""

    ico = st.session_state.get("selected_ico", "")

    # ── Výběr klienta ──────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,{CITI_BLUE} 0%,#0066CC 100%);
             color:white;padding:1.2rem 1.5rem;border-radius:10px;margin-bottom:1rem">
            <h2 style="margin:0;font-size:1.4rem">📄 Credit Memo Generator</h2>
            <p style="margin:0.2rem 0 0;font-size:0.85rem;opacity:0.85">
                AI-asistovaná tvorba kreditního mema · 4-Eyes Rule
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    from utils.mock_data import get_portfolio
    portfolio = get_portfolio()
    ico_options = [f"{c['ico']} — {c['company_name']}" for c in portfolio]
    ico_map = {f"{c['ico']} — {c['company_name']}": c["ico"] for c in portfolio}

    default_idx = 0
    if ico:
        matching = [i for i, opt in enumerate(ico_options) if opt.startswith(ico)]
        if matching:
            default_idx = matching[0]

    selected_label = st.selectbox(
        "Vyberte klienta",
        options=ico_options,
        index=default_idx,
        key="memo_ico_select",
    )
    selected_ico = ico_map[selected_label]

    # Tlačítko spuštění pipeline
    col_btn, col_mode = st.columns([2, 3])
    with col_btn:
        run_btn = st.button("🚀 Spustit AI Pipeline", type="primary", key="run_pipeline_btn")
    with col_mode:
        use_real_api = st.checkbox(
            "Použít Real AI (Claude API)",
            value=False,
            help="Bez zaškrtnutí použije demo mode (mock data, bez API volání)",
        )

    # State management pro výsledek pipeline
    result_key = f"pipeline_result_{selected_ico}"

    if run_btn:
        with st.spinner("⏳ Zpracovávám pipeline... (Demo mode)"):
            if use_real_api:
                try:
                    from pipeline.graph import run_pipeline
                    result = run_pipeline(selected_ico)
                except Exception as e:
                    st.error(f"Pipeline selhala: {e}")
                    return
            else:
                # Demo mode — mock výsledek
                result = get_mock_agent_result(selected_ico)

        st.session_state[result_key] = result
        st.session_state["selected_ico"] = selected_ico
        st.success("✅ Pipeline dokončena")

    result = st.session_state.get(result_key)
    if result is None:
        st.info("👆 Vyberte klienta a spusťte pipeline.")
        return

    # ── Zobrazení výsledku ─────────────────────────────────────────────────────
    _render_pipeline_result(result, selected_ico)


def _render_pipeline_result(result: dict, ico: str) -> None:
    """Renderuje výsledek pipeline: status, WCR, memo, checker."""

    status = str(result.get("status", ""))
    company = result.get("company_name", result.get("case_view", {}).get("company_name", ico))

    # Status bar
    status_colors = {
        "awaiting_human": "#8B5CF6",
        "completed": "#16A34A",
        "failed": "#DC2626",
        "frozen": "#6B7280",
        "escalated": "#F59E0B",
        "running": "#3B82F6",
    }
    status_key = status.split(".")[-1].lower() if "." in status else status.lower()
    color = status_colors.get(status_key, "#6B7280")
    st.markdown(
        f"<div style='background:{color};color:white;padding:0.6rem 1rem;"
        f"border-radius:8px;margin-bottom:1rem;font-weight:600'>"
        f"Status: {status.upper()} — {company} (IČO: {ico})</div>",
        unsafe_allow_html=True,
    )

    # Tabs
    tab_memo, tab_wcr, tab_checker, tab_metrics = st.tabs([
        "📄 Credit Memo",
        "🔒 WCR Rules",
        "🔍 Quality Check",
        "📊 Finanční metriky",
    ])

    with tab_memo:
        _render_memo_tab(result)

    with tab_wcr:
        _render_wcr_tab(result)

    with tab_checker:
        _render_checker_tab(result)

    with tab_metrics:
        _render_metrics_tab(result, ico)


def _render_memo_tab(result: dict) -> None:
    """Renderuje Credit Memo s zvýrazněnými citacemi."""
    draft_memo = result.get("draft_memo", "")
    if not draft_memo:
        st.warning("Memo nebylo vygenerováno.")
        return

    iteration = result.get("maker_iteration", 1)
    st.caption(f"Iterace Makera: {iteration} · Stav: {result.get('checker_verdict', 'N/A')}")

    # Toggle: raw nebo zvýrazněné citace
    highlight = st.checkbox("Zvýraznit [CITATION:] tagy", value=True, key="highlight_citations")

    if highlight:
        html_memo = highlight_citations(draft_memo.replace("\n", "<br>"))
        st.markdown(
            f"<div class='memo-container' style='background:white;border:1px solid #E5E7EB;"
            f"border-radius:10px;padding:1.5rem 2rem;line-height:1.7'>{html_memo}</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(draft_memo)

    # Download
    st.download_button(
        "⬇️ Stáhnout memo (.md)",
        data=draft_memo,
        file_name=f"credit_memo_{result.get('ico', 'unknown')}.md",
        mime="text/markdown",
    )


def _render_wcr_tab(result: dict) -> None:
    """Renderuje WCR Rules výsledek."""
    wcr_report = result.get("wcr_report")
    if not wcr_report:
        st.info("WCR report není k dispozici.")
        return

    wcr_passed = result.get("wcr_passed", True)
    overall_icon = "✅" if wcr_passed else "❌"
    overall_color = "#16A34A" if wcr_passed else "#DC2626"

    st.markdown(
        f"<div style='background:{overall_color};color:white;padding:0.8rem 1rem;"
        f"border-radius:8px;font-weight:700;font-size:1.1rem;margin-bottom:1rem'>"
        f"{overall_icon} WCR Status: {'PASS — všechna pravidla splněna' if wcr_passed else 'FAIL — porušení nalezena'}"
        f"</div>",
        unsafe_allow_html=True,
    )

    # Souhrnné číselné ukazatele
    c1, c2, c3 = st.columns(3)
    c1.metric("Pravidel celkem", wcr_report.get("total_rules", 5))
    c2.metric("Splněno ✅", wcr_report.get("passed_rules", 0))
    c3.metric("Porušeno ❌", wcr_report.get("failed_rules", 0))

    st.markdown("#### Detailní přehled pravidel")
    for rule in wcr_report.get("rules", []):
        passed = rule.get("passed", True)
        row_bg = "#F0FDF4" if passed else "#FEF2F2"
        icon = "✅" if passed else "❌"
        unit = rule.get("unit", "")
        val = rule.get("value", "N/A")
        lim = rule.get("limit", "N/A")

        st.markdown(
            f"<div style='background:{row_bg};border-radius:6px;padding:0.6rem 0.8rem;"
            f"margin:0.3rem 0;display:flex;align-items:center'>"
            f"<span style='font-size:1.1rem;margin-right:0.5rem'>{icon}</span>"
            f"<div><strong>{rule.get('description', '')}</strong><br>"
            f"<span style='font-size:0.85rem;color:#6B7280'>"
            f"Hodnota: <strong>{val}{unit}</strong> · Limit: {lim}{unit}</span></div>"
            f"</div>",
            unsafe_allow_html=True,
        )


def _render_checker_tab(result: dict) -> None:
    """Renderuje Quality Control Checker výsledek."""
    verdict = result.get("checker_verdict", "N/A")
    coverage = result.get("citation_coverage", 0.0)
    hallucinations = result.get("hallucination_report", [])

    verdict_color = "#16A34A" if verdict == "pass" else "#DC2626"
    verdict_icon = "✅" if verdict == "pass" else "❌"

    st.markdown(
        f"<div style='background:{verdict_color};color:white;padding:0.8rem 1rem;"
        f"border-radius:8px;font-weight:700;margin-bottom:1rem'>"
        f"{verdict_icon} Checker verdict: {verdict.upper()}</div>",
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("Citation Coverage", fmt_pct(coverage * 100))
    col2.metric("Min. požadováno", "90.0 %")
    col3.metric("Halucinace", len(hallucinations))

    if hallucinations:
        st.markdown("#### Nalezené problémy")
        for issue in hallucinations:
            st.error(issue)
    else:
        st.success("✅ Žádné halucinace ani neplatné citace nenalezeny.")

    iteration = result.get("maker_iteration", 1)
    if iteration > 1:
        st.info(f"ℹ️ Memo bylo re-generováno {iteration}× (Maker-Checker loop)")


def _render_metrics_tab(result: dict, ico: str) -> None:
    """Renderuje finanční metriky klienta."""
    metrics = result.get("financial_metrics", {})
    case_view = result.get("case_view", {})
    client = get_client(ico)

    if not metrics and not case_view:
        st.info("Metriky nejsou k dispozici.")
        return

    st.markdown("#### Klíčové finanční ukazatele (vypočteno deterministicky)")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Leverage Ratio", f"{metrics.get('leverage_ratio', 'N/A')}x")
    col2.metric("DSCR", metrics.get("dscr", "N/A"))
    col3.metric("Current Ratio", metrics.get("current_ratio", "N/A"))
    col4.metric("Využití limitu", fmt_pct(metrics.get("utilisation_pct")))

    if client:
        st.markdown("#### Základní finanční data (zdroj: CBS 2024)")
        fd = client.get("financial_data", {})
        data_table = {
            "Ukazatel": ["Obrat", "EBITDA", "Čistý dluh", "Celková aktiva",
                         "Oběžná aktiva", "Kr. závazky", "Debt Service", "Op. Cash Flow"],
            "Hodnota": [
                fmt_czk(fd.get("revenue")),
                fmt_czk(fd.get("ebitda")),
                fmt_czk(fd.get("net_debt")),
                fmt_czk(fd.get("total_assets")),
                fmt_czk(fd.get("current_assets")),
                fmt_czk(fd.get("current_liabilities")),
                fmt_czk(fd.get("debt_service")),
                fmt_czk(fd.get("operating_cashflow")),
            ],
        }
        st.dataframe(data_table, use_container_width=True)

    # Data sources
    sources = case_view.get("data_sources") or (client or {}).get("data_sources", {})
    if sources:
        st.markdown("#### Zdroje dat")
        for source_id, description in sources.items():
            st.markdown(f"- `{source_id}`: {description}")
