"""
Cases Log — ui/page_cases_log.py
Přehled všech zpracovaných pipeline kейсů v aktuální session.
"""

import streamlit as st

from ui.styles import CITI_BLUE


def render_cases_log_page() -> None:
    """Renderuje stránku s logem všech zpracovaných kейсů."""

    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,{CITI_BLUE} 0%,#0066CC 100%);
             color:white;padding:1.2rem 1.5rem;border-radius:10px;margin-bottom:1rem">
            <h2 style="margin:0;font-size:1.4rem">📋 Cases Log</h2>
            <p style="margin:0.2rem 0 0;font-size:0.85rem;opacity:0.85">
                Log zpracovaných kreditních memos · Horizon Bank
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    cases_log = st.session_state.get("cases_log", [])

    if not cases_log:
        st.info("Zatím žádné zpracované kейсы. Spusťte pipeline na stránce 📄 Credit Memo.")
        return

    # ── Souhrnné KPI ──────────────────────────────────────────────────────────
    total     = len(cases_log)
    approved  = sum(1 for c in cases_log if c.get("human_decision") == "approve")
    rejected  = sum(1 for c in cases_log if c.get("human_decision") == "reject")
    pending   = sum(1 for c in cases_log if not c.get("human_decision"))
    wcr_fail  = sum(1 for c in cases_log if c.get("wcr_passed") is False)

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Celkem případů", total)
    k2.metric("✅ Schváleno", approved)
    k3.metric("❌ Zamítnuto", rejected)
    k4.metric("⏳ Čeká na rozhodnutí", pending)
    k5.metric("⚠️ WCR Fail", wcr_fail)

    st.markdown("---")

    # ── Filtr ─────────────────────────────────────────────────────────────────
    col_f1, col_f2 = st.columns([2, 3])
    with col_f1:
        decision_filter = st.selectbox(
            "Filtr rozhodnutí",
            options=["Vše", "Čeká na rozhodnutí", "Schváleno", "Podmínečně", "Zamítnuto"],
            key="cases_decision_filter",
        )
    with col_f2:
        search_log = st.text_input("🔍 Hledat (název / IČO)", key="cases_search")

    filtered = cases_log
    if decision_filter == "Čeká na rozhodnutí":
        filtered = [c for c in filtered if not c.get("human_decision")]
    elif decision_filter == "Schváleno":
        filtered = [c for c in filtered if c.get("human_decision") == "approve"]
    elif decision_filter == "Podmínečně":
        filtered = [c for c in filtered if c.get("human_decision") == "approve_with_conditions"]
    elif decision_filter == "Zamítnuto":
        filtered = [c for c in filtered if c.get("human_decision") == "reject"]

    if search_log.strip():
        q = search_log.strip().lower()
        filtered = [c for c in filtered if q in c.get("company_name", "").lower() or q in c.get("ico", "")]

    if not filtered:
        st.warning("Žádné záznamy pro vybraný filtr.")
        return

    # ── Tabulka kейсů ─────────────────────────────────────────────────────────
    for case in filtered:
        _render_case_row(case)


def _render_case_row(case: dict) -> None:
    ico           = case.get("ico", "—")
    company       = case.get("company_name", ico)
    status        = case.get("status", "")
    status_key    = status.split(".")[-1].lower() if "." in status else status.lower()
    created_at    = case.get("created_at", "")[:19].replace("T", " ") if case.get("created_at") else "—"
    mode          = case.get("mode", "demo")
    wcr_passed    = case.get("wcr_passed")
    checker       = case.get("checker_verdict", "N/A")
    decision      = case.get("human_decision")
    request_id    = case.get("request_id", "—")

    # Status pipeline
    status_colors = {
        "awaiting_human": "#8B5CF6",
        "completed":      "#16A34A",
        "failed":         "#DC2626",
        "frozen":         "#6B7280",
        "escalated":      "#F59E0B",
    }
    s_color = status_colors.get(status_key, "#6B7280")

    # Human decision
    dec_colors = {
        "approve":                 "#16A34A",
        "reject":                  "#DC2626",
        "approve_with_conditions": "#D97706",
    }
    dec_labels = {
        "approve":                 "✅ Schváleno",
        "reject":                  "❌ Zamítnuto",
        "approve_with_conditions": "⚠️ Podmínečně",
    }
    dec_color = dec_colors.get(decision, "#6B7280")
    dec_label = dec_labels.get(decision, "⏳ Čeká")

    with st.container():
        col_info, col_status, col_metrics, col_action = st.columns([3, 2, 3, 2])

        with col_info:
            mode_badge = "🤖 Real AI" if mode == "real_ai" else "🎭 Demo"
            st.markdown(
                f"**{company}**  \n"
                f"`{ico}` · {mode_badge}  \n"
                f"<span style='font-size:0.8rem;color:#9CA3AF'>{created_at}</span>",
                unsafe_allow_html=True,
            )

        with col_status:
            st.markdown(
                f"<div style='font-size:0.8rem'>"
                f"<span style='background:{s_color};color:white;padding:2px 8px;"
                f"border-radius:4px;font-weight:600'>{status_key.upper()}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
            wcr_icon_str = "✅ WCR PASS" if wcr_passed else ("❌ WCR FAIL" if wcr_passed is False else "— WCR N/A")
            st.markdown(
                f"<div style='font-size:0.8rem;margin-top:0.3rem'>{wcr_icon_str}</div>",
                unsafe_allow_html=True,
            )

        with col_metrics:
            checker_color = "#16A34A" if checker == "pass" else "#DC2626"
            st.markdown(
                f"<div style='font-size:0.8rem'>"
                f"Checker: <span style='color:{checker_color};font-weight:600'>{checker.upper() if checker else 'N/A'}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<div style='font-size:0.75rem;color:#9CA3AF'>ID: {request_id}</div>",
                unsafe_allow_html=True,
            )

        with col_action:
            st.markdown(
                f"<div style='background:{dec_color};color:white;padding:4px 10px;"
                f"border-radius:6px;font-size:0.8rem;font-weight:600;text-align:center'>"
                f"{dec_label}</div>",
                unsafe_allow_html=True,
            )
            if st.button("📄 Otevřít", key=f"open_case_{ico}", use_container_width=True):
                st.session_state["selected_ico"] = ico
                st.session_state["page"] = "credit_memo"
                st.rerun()

    st.markdown(
        "<hr style='border:none;border-top:1px solid #E5E7EB;margin:0.4rem 0'>",
        unsafe_allow_html=True,
    )
