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
from utils.data_connector import get_client_info, get_portfolio_clients
from utils.mock_data import get_mock_agent_result


@st.cache_data(ttl=300)
def _load_portfolio() -> list[dict]:
    return get_portfolio_clients()


def render_credit_memo_page() -> None:
    """Renderuje Credit Memo stránku pro vybrané IČO."""

    ico = st.session_state.get("selected_ico", "")

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

    portfolio = _load_portfolio()
    if not portfolio:
        st.error("Portfolio je prázdné — nepodařilo se načíst klienty z Databricks.")
        return

    # ── Vyhledávání klienta ────────────────────────────────────────────────────
    search = st.text_input(
        "🔍 Hledat klienta (název nebo IČO)",
        placeholder="Např. Tech Data nebo 23110303",
        key="client_search",
    )

    filtered_portfolio = portfolio
    if search.strip():
        q = search.strip().lower()
        filtered_portfolio = [
            c for c in portfolio
            if q in c["company_name"].lower() or q in c["ico"]
        ]

    if not filtered_portfolio:
        st.warning(f"Žádný klient nenalezen pro: '{search}'")
        return

    ico_options = [f"{c['ico']} — {c['company_name']}" for c in filtered_portfolio]
    ico_map = {f"{c['ico']} — {c['company_name']}": c["ico"] for c in filtered_portfolio}

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
    if selected_label is None:
        st.info("👆 Vyberte klienta ze seznamu.")
        return
    selected_ico = ico_map[selected_label]

    # ── Tlačítko spuštění + přepínač AI ───────────────────────────────────────
    col_btn, col_mode = st.columns([2, 3])
    with col_btn:
        run_btn = st.button("🚀 Spustit AI Pipeline", type="primary", key="run_pipeline_btn")
    with col_mode:
        use_real_api = st.checkbox(
            "Použít Real AI",
            value=False,
            help="Bez zaškrtnutí použije demo mode (mock data, bez API volání)",
        )

    result_key = f"pipeline_result_{selected_ico}"

    if run_btn:
        if use_real_api:
            with st.status("⏳ Pipeline běží — Real AI mode...", expanded=True) as pipeline_status:
                st.markdown(
                    "Probíhající fáze:\n\n"
                    "- 🔍 **Fáze 1** — DataExtractor: načítám finanční data z Databricks\n"
                    "- 📊 **Fáze 2** — ContextBuilder + CreditAnalysis (DSCR, Leverage, WCR)\n"
                    "- ✍️ **Fáze 3** — MemoPreparation Agent: generuji kreditní memo *(AI)*\n"
                    "- 🔎 **Fáze 3b** — QualityControl Checker: citace a halucinace *(AI)*\n"
                    "- 📋 **Fáze 4** — PolicyRules + Human Review queue\n"
                )
                try:
                    from pipeline.graph import run_pipeline
                    result = run_pipeline(selected_ico)
                    pipeline_status.update(
                        label="✅ Pipeline dokončena!", state="complete", expanded=False
                    )
                except Exception as e:
                    pipeline_status.update(label="❌ Pipeline selhala", state="error")
                    st.error(f"Chyba: {e}")
                    return
        else:
            with st.spinner("⏳ Demo mode — generuji mock výsledek..."):
                result = get_mock_agent_result(selected_ico)

        st.session_state[result_key] = result
        st.session_state["selected_ico"] = selected_ico
        # Uložíme do global cases logu
        cases_log = st.session_state.get("cases_log", [])
        cases_log = [c for c in cases_log if c.get("ico") != selected_ico]  # dedupe
        cases_log.insert(0, {
            "ico":          selected_ico,
            "company_name": result.get("company_name", selected_ico),
            "status":       str(result.get("status", "")),
            "request_id":   result.get("request_id", ""),
            "created_at":   result.get("created_at", ""),
            "mode":         "real_ai" if use_real_api else "demo",
            "wcr_passed":   result.get("wcr_passed"),
            "checker_verdict": result.get("checker_verdict"),
        })
        st.session_state["cases_log"] = cases_log[:50]  # max 50 záznamů
        st.success("✅ Pipeline dokončena")

    result = st.session_state.get(result_key)
    if result is None:
        st.info("👆 Vyberte klienta a spusťte pipeline.")
        return

    _render_pipeline_result(result, selected_ico)


def _render_pipeline_result(result: dict, ico: str) -> None:
    """Renderuje výsledek pipeline: status, WCR, memo, checker, human action."""

    status = str(result.get("status", ""))
    company = result.get("company_name", result.get("case_view", {}).get("company_name", ico))

    status_colors = {
        "awaiting_human": "#8B5CF6",
        "completed":      "#16A34A",
        "failed":         "#DC2626",
        "frozen":         "#6B7280",
        "escalated":      "#F59E0B",
        "running":        "#3B82F6",
    }
    status_key = status.split(".")[-1].lower() if "." in status else status.lower()
    color = status_colors.get(status_key, "#6B7280")
    st.markdown(
        f"<div style='background:{color};color:white;padding:0.6rem 1rem;"
        f"border-radius:8px;margin-bottom:1rem;font-weight:600'>"
        f"Status: {status.upper()} — {company} (IČO: {ico})</div>",
        unsafe_allow_html=True,
    )

    tab_memo, tab_wcr, tab_checker, tab_metrics, tab_audit = st.tabs([
        "📄 Credit Memo",
        "🔒 WCR Rules",
        "🔍 Quality Check",
        "📊 Finanční metriky",
        "🔎 Agent Log",
    ])

    with tab_memo:
        _render_memo_tab(result)

    with tab_wcr:
        _render_wcr_tab(result)

    with tab_checker:
        _render_checker_tab(result)

    with tab_metrics:
        _render_metrics_tab(result, ico)

    with tab_audit:
        _render_agent_log_tab(result)

    # ── Human Decision Panel ───────────────────────────────────────────────────
    st.markdown("---")
    _render_human_decision_panel(result, ico)


def _render_human_decision_panel(result: dict, ico: str) -> None:
    """Inline human decision (4-Eyes Rule) přímo na Credit Memo stránce."""
    decision_key = f"decision_{ico}"
    existing = st.session_state.get(decision_key)

    st.markdown("### 👁️ Human Review — 4-Eyes Rule")

    wcr_passed = result.get("wcr_passed", True)
    checker_verdict = result.get("checker_verdict", "N/A")
    breaches = result.get("wcr_report", {}).get("breaches", [])

    col1, col2, col3 = st.columns(3)
    col1.metric("WCR Status", "✅ PASS" if wcr_passed else f"❌ {len(breaches)} breach")
    col2.metric("AI Checker", checker_verdict.upper() if checker_verdict else "N/A")
    col3.metric("Stav pipeline", status_key := (str(result.get("status", "")).split(".")[-1].upper()))

    if existing:
        dec_colors = {
            "approve":                  "#16A34A",
            "reject":                   "#DC2626",
            "approve_with_conditions":  "#D97706",
        }
        dec_labels = {
            "approve":                  "✅ SCHVÁLENO",
            "reject":                   "❌ ZAMÍTNUTO",
            "approve_with_conditions":  "⚠️ PODMÍNEČNĚ SCHVÁLENO",
        }
        c = dec_colors.get(existing["decision"], "#6B7280")
        l = dec_labels.get(existing["decision"], existing["decision"])
        st.markdown(
            f"<div style='background:{c};color:white;padding:0.8rem 1.2rem;"
            f"border-radius:8px;font-weight:700;font-size:1rem;margin:0.5rem 0'>"
            f"{l}</div>",
            unsafe_allow_html=True,
        )
        if existing.get("comments"):
            st.markdown(f"**Komentář:** {existing['comments']}")
        if st.button("🔄 Změnit rozhodnutí", key=f"change_dec_memo_{ico}"):
            del st.session_state[decision_key]
            st.rerun()
        return

    comments = st.text_area(
        "Komentář underwritera (volitelné)",
        placeholder="Např.: Doporučuji schválit s podmínkou pravidelného reportingu...",
        key=f"comments_memo_{ico}",
        height=80,
    )

    if not wcr_passed:
        st.warning(f"⚠️ {len(breaches)} WCR porušení — zkontrolujte WCR Rules před rozhodnutím.")

    col_a, col_c, col_r = st.columns(3)
    with col_a:
        if st.button("✅ Schválit", key=f"approve_memo_{ico}", type="primary", use_container_width=True):
            _record_decision(ico, "approve", comments)
    with col_c:
        if st.button("⚠️ Podmínečně", key=f"cond_memo_{ico}", use_container_width=True):
            _record_decision(ico, "approve_with_conditions", comments)
    with col_r:
        if st.button("❌ Zamítnout", key=f"reject_memo_{ico}", use_container_width=True):
            _record_decision(ico, "reject", comments)


def _record_decision(ico: str, decision: str, comments: str) -> None:
    from pipeline.nodes.phase4_human_audit import record_human_decision
    result_key  = f"pipeline_result_{ico}"
    decision_key = f"decision_{ico}"
    result = st.session_state.get(result_key, {})
    updated = record_human_decision(result, decision, comments)
    st.session_state[result_key] = updated
    st.session_state[decision_key] = {"decision": decision, "comments": comments}
    # Aktualizace cases logu
    cases_log = st.session_state.get("cases_log", [])
    for case in cases_log:
        if case.get("ico") == ico:
            case["human_decision"] = decision
            break
    st.session_state["cases_log"] = cases_log
    st.rerun()


def _render_memo_tab(result: dict) -> None:
    draft_memo = result.get("draft_memo", "")
    if not draft_memo:
        st.warning("Memo nebylo vygenerováno.")
        return

    iteration = result.get("maker_iteration", 1)
    st.caption(f"Iterace Makera: {iteration} · Stav: {result.get('checker_verdict', 'N/A')}")

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

    st.download_button(
        "⬇️ Stáhnout memo (.md)",
        data=draft_memo,
        file_name=f"credit_memo_{result.get('ico', 'unknown')}.md",
        mime="text/markdown",
    )


def _render_wcr_tab(result: dict) -> None:
    wcr_report = result.get("wcr_report")
    if not wcr_report:
        st.info("WCR report není k dispozici.")
        return

    wcr_passed = result.get("wcr_passed", True)
    overall_icon  = "✅" if wcr_passed else "❌"
    overall_color = "#16A34A" if wcr_passed else "#DC2626"
    st.markdown(
        f"<div style='background:{overall_color};color:white;padding:0.8rem 1rem;"
        f"border-radius:8px;font-weight:700;font-size:1.1rem;margin-bottom:1rem'>"
        f"{overall_icon} WCR Status: {'PASS — všechna pravidla splněna' if wcr_passed else 'FAIL — porušení nalezena'}"
        f"</div>",
        unsafe_allow_html=True,
    )
    total    = wcr_report.get("total_rules", 5)
    passed_n = wcr_report.get("passed_rules", 0)
    failed_n = wcr_report.get("failed_rules", 0)
    skipped_n = sum(1 for r in wcr_report.get("rules", []) if r.get("skipped"))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Pravidel celkem", total)
    c2.metric("Splněno ✅", passed_n)
    c3.metric("Porušeno ❌", failed_n)
    c4.metric("Čeká na CRIBIS ⏭️", skipped_n)

    if wcr_report.get("wcr_partial"):
        st.info(
            f"ℹ️ **Částečné hodnocení** — {wcr_report.get('data_completeness', '')}. "
            "Leverage, DSCR a Current Ratio vyžadují CRIBIS data od Týmu 8."
        )

    st.markdown("#### Detailní přehled pravidel")
    for rule in wcr_report.get("rules", []):
        passed = rule.get("passed")       # True / False / None (skipped)
        skipped = rule.get("skipped", False)
        unit   = rule.get("unit", "")
        val    = rule.get("value")
        lim    = rule.get("limit", "N/A")
        note   = rule.get("note", "")
        desc   = rule.get("description", "")

        if skipped or passed is None:
            row_bg = "#F9FAFB"
            icon   = "⏭️"
            val_str = "N/A"
            lim_str = f"≤ {lim}{unit}" if "Limit" not in str(lim) else str(lim)
            extra   = f" · <em style='color:#9CA3AF'>{note}</em>" if note else ""
        elif passed:
            row_bg  = "#F0FDF4"
            icon    = "✅"
            val_str = f"{val}{unit}"
            lim_str = f"{lim}{unit}"
            extra   = ""
        else:
            row_bg  = "#FEF2F2"
            icon    = "❌"
            val_str = f"{val}{unit}"
            lim_str = f"{lim}{unit}"
            extra   = ""

        st.markdown(
            f"<div style='background:{row_bg};border-radius:6px;padding:0.6rem 0.8rem;"
            f"margin:0.3rem 0;border-left:3px solid "
            f"{'#16A34A' if passed is True else ('#DC2626' if passed is False else '#9CA3AF')}'>"
            f"<span style='font-size:1.1rem;margin-right:0.5rem'>{icon}</span>"
            f"<strong>{desc}</strong><br>"
            f"<span style='font-size:0.85rem;color:#6B7280'>"
            f"Hodnota: <strong>{val_str}</strong> · Limit: {lim_str}{extra}</span></div>",
            unsafe_allow_html=True,
        )


def _render_checker_tab(result: dict) -> None:
    verdict       = result.get("checker_verdict", "N/A")
    coverage      = result.get("citation_coverage", 0.0)
    hallucinations = result.get("hallucination_report", [])

    verdict_color = "#16A34A" if verdict == "pass" else "#DC2626"
    verdict_icon  = "✅" if verdict == "pass" else "❌"
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
    metrics   = result.get("financial_metrics") or {}
    case_view = result.get("case_view") or {}
    wcr_report = result.get("wcr_report") or {}

    st.markdown("#### Klíčové finanční ukazatele (vypočteno deterministicky)")

    # ── Metriky z pipeline state ───────────────────────────────────────────────
    lev  = metrics.get("leverage_ratio")
    dscr = metrics.get("dscr")
    cr   = metrics.get("current_ratio")
    util = metrics.get("utilisation_pct") or metrics.get("credit_limit_utilization_pct")
    dpd  = metrics.get("dpd_current")

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Leverage", f"{lev}x" if lev is not None else "N/A",
                help="Net Debt / EBITDA · zdroj: CRIBIS")
    col2.metric("DSCR", f"{dscr}" if dscr is not None else "N/A",
                help="Op. CF / Debt Service · zdroj: CRIBIS")
    col3.metric("Current Ratio", f"{cr}" if cr is not None else "N/A",
                help="Oběžná aktiva / Kr. závazky · zdroj: CRIBIS")
    col4.metric("Využití limitu", fmt_pct(util) if util is not None else "N/A",
                help="zdroj: Silver credit_history")
    col5.metric("DPD", f"{dpd} dní" if dpd is not None else "N/A",
                help="Days Past Due · zdroj: Silver credit_history")

    if lev is None and dscr is None and cr is None:
        st.info(
            "ℹ️ Leverage, DSCR a Current Ratio nejsou dostupné — vyžadují CRIBIS data (Tým 8).  \n"
            "Spusťte diagnostiku v **⚙️ Nastavení → Databricks → CRIBIS test**."
        )

    # ── Raw finanční data z CRIBIS (přes case_view nebo metrics) ──────────────
    cribis_raw = case_view.get("cribis_data") or metrics.get("cribis_raw") or {}
    raw_items = [
        ("Obrat",           cribis_raw.get("revenue")),
        ("EBITDA",          cribis_raw.get("ebitda")),
        ("Čistý dluh",      cribis_raw.get("net_debt")),
        ("Celková aktiva",  cribis_raw.get("total_assets")),
        ("Oběžná aktiva",   cribis_raw.get("current_assets")),
        ("Celkový dluh",    cribis_raw.get("total_debt")),
        ("Vlastní kapitál", cribis_raw.get("equity")),
        ("Úrok. náklady",   cribis_raw.get("interest_expense")),
    ]
    available_raw = [(k, v) for k, v in raw_items if v is not None]
    if available_raw:
        st.markdown("#### Základní finanční data (CRIBIS)")
        st.dataframe(
            {"Ukazatel": [k for k, _ in available_raw],
             "Hodnota":  [fmt_czk(v) for _, v in available_raw]},
            use_container_width=True,
        )

    # ── Silver data (utilisation, DPD) ────────────────────────────────────────
    if util is not None or dpd is not None:
        st.markdown("#### Silver data")
        silver_items = []
        if util is not None:
            silver_items.append(("Využití limitu", fmt_pct(util)))
        if dpd is not None:
            silver_items.append(("DPD", f"{dpd} dní"))
        avg_turn = metrics.get("avg_monthly_turnover")
        if avg_turn:
            silver_items.append(("Prům. měs. obrat", fmt_czk(avg_turn)))
        if silver_items:
            st.dataframe(
                {"Ukazatel": [k for k, _ in silver_items],
                 "Hodnota":  [v for _, v in silver_items]},
                use_container_width=True,
            )

    # ── WCR data completeness ──────────────────────────────────────────────────
    if wcr_report.get("data_completeness"):
        st.caption(f"📊 {wcr_report['data_completeness']} · {wcr_report.get('checked_at', '')[:19]}")

    # ── Zdroje dat ────────────────────────────────────────────────────────────
    sources = case_view.get("data_sources") or {}
    if sources:
        st.markdown("#### Zdroje dat")
        for source_id, description in sources.items():
            st.markdown(f"- `{source_id}`: {description}")


def _render_agent_log_tab(result: dict) -> None:
    audit_trail = result.get("audit_trail", [])
    if not audit_trail:
        st.info("Audit log není k dispozici (spusťte pipeline s 'Použít Real AI').")
        return

    ai_steps     = [e for e in audit_trail if e.get("prompt_hash")]
    det_steps    = [e for e in audit_trail if not e.get("prompt_hash")]
    total_tokens = sum(e.get("tokens_used") or 0 for e in audit_trail)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Kroků celkem", len(audit_trail))
    c2.metric("🤖 AI uzly", len(ai_steps))
    c3.metric("⚙️ DET uzly", len(det_steps))
    c4.metric("Tokeny", f"{total_tokens:,}" if total_tokens else "—")

    st.markdown("---")

    result_colors = {"success": "#16A34A", "pass": "#16A34A", "failed": "#DC2626",
                     "frozen": "#6B7280", "escalated": "#F59E0B", "error": "#DC2626"}
    result_icons  = {"success": "✅", "pass": "✅", "failed": "❌",
                     "frozen": "🧊", "escalated": "⚠️", "error": "❌"}

    for i, event in enumerate(audit_trail, 1):
        node        = event.get("node", "—")
        action      = event.get("action", "—")
        res         = str(event.get("result", "")).lower()
        prompt_hash = event.get("prompt_hash")
        prompt_ver  = event.get("prompt_version")
        tokens      = event.get("tokens_used")
        ts          = event.get("timestamp", "")
        meta        = event.get("metadata") or {}

        node_type = "🤖 AI" if prompt_hash else "⚙️ DET"
        res_icon  = result_icons.get(res, "•")
        res_color = result_colors.get(res, "#6B7280")
        ts_short  = ts[11:19] if len(ts) >= 19 else ts

        col_idx, col_main, col_meta = st.columns([0.4, 5, 2])
        with col_idx:
            st.markdown(
                f"<div style='text-align:center;font-size:0.8rem;color:#9CA3AF;"
                f"padding-top:0.4rem'>{i:02d}</div>", unsafe_allow_html=True)
        with col_main:
            badge_color = "#3B82F6" if prompt_hash else "#6B7280"
            st.markdown(
                f"<div style='padding:0.5rem 0.8rem;border-left:3px solid {res_color};"
                f"background:#F9FAFB;border-radius:0 6px 6px 0;margin-bottom:2px'>"
                f"<span style='background:{badge_color};color:white;font-size:0.7rem;"
                f"padding:1px 6px;border-radius:4px;margin-right:6px'>{node_type}</span>"
                f"<strong>{node}</strong> "
                f"<span style='color:#6B7280;font-size:0.85rem'>→ {action}</span>"
                f"<span style='float:right;color:{res_color};font-weight:600'>"
                f"{res_icon} {res.upper()}</span></div>",
                unsafe_allow_html=True,
            )
        with col_meta:
            parts = []
            if ts_short: parts.append(f"⏱ {ts_short}")
            if tokens:   parts.append(f"~{tokens:,} tok")
            if prompt_hash: parts.append(f"`{prompt_hash}`")
            if prompt_ver:  parts.append(f"v{prompt_ver}")
            st.markdown(
                f"<div style='font-size:0.75rem;color:#9CA3AF;padding-top:0.4rem'>"
                + " · ".join(parts) + "</div>", unsafe_allow_html=True)

        if meta:
            with st.expander(f"Detail — krok {i:02d}: {node}", expanded=False):
                for k, v in meta.items():
                    st.markdown(f"- **{k}**: `{v}`")
