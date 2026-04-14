"""
Early Warning System Dashboard — ui/page_early_warning.py
EWS LangGraph pipeline UI · ICM GenAI Platform · Tým 7
"""

import streamlit as st

from ui.styles import (
    CITI_BLUE,
    EW_COLORS,
    CITI_GRAY,
    ew_badge_html,
    fmt_pct,
)


def render_early_warning_page() -> None:
    """Renderuje Early Warning System Dashboard."""

    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,{CITI_BLUE} 0%,#0066CC 100%);
             color:white;padding:1.2rem 1.5rem;border-radius:10px;margin-bottom:1rem">
            <h2 style="margin:0;font-size:1.4rem">⚠️ Early Warning System</h2>
            <p style="margin:0.2rem 0 0;font-size:0.85rem;opacity:0.85">
                LangGraph EWS Pipeline · DETERMINISTIC pravidla + volitelný AI komentář
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Spuštění pipeline ──────────────────────────────────────────────────────
    col_run, col_type, col_spacer = st.columns([2, 2, 4])
    with col_run:
        run_btn = st.button("▶ Spustit EWS pipeline", type="primary", use_container_width=True)
    with col_type:
        run_type = st.selectbox(
            "Typ běhu",
            options=["on_demand", "daily_batch"],
            index=0,
            label_visibility="collapsed",
        )

    # ── Výsledky v session state ───────────────────────────────────────────────
    if run_btn:
        with st.spinner("Spouštím EWS LangGraph pipeline…"):
            try:
                from early_warning.graph import run_early_warning
                result = run_early_warning(run_type)
                st.session_state["ews_result"] = result
            except Exception as exc:
                st.error(f"EWS pipeline selhala: {exc}")
                st.session_state.pop("ews_result", None)

    result = st.session_state.get("ews_result")

    if result is None:
        st.info("Stiskněte **▶ Spustit EWS pipeline** pro spuštění analýzy portfolia.")
        return

    summary = result.get("summary", {})
    alerts  = result.get("alerts", [])

    # ── KPI karty ─────────────────────────────────────────────────────────────
    st.markdown("---")
    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        st.metric("Klientů celkem", summary.get("total_clients", 0))
    with k2:
        st.metric("🔴 RED", summary.get("red_alerts", 0))
    with k3:
        st.metric("🟡 AMBER", summary.get("amber_alerts", 0))
    with k4:
        st.metric("🟢 GREEN", summary.get("green_clients", 0))
    with k5:
        st.metric("Alertů", len(alerts))

    st.markdown("---")

    # ── Filtr alertů ──────────────────────────────────────────────────────────
    level_filter = st.radio(
        "Filtr úrovně",
        options=["Vše", "RED", "AMBER", "GREEN"],
        horizontal=True,
        index=0,
    )

    filtered = alerts if level_filter == "Vše" else [
        a for a in alerts if a.get("alert_level") == level_filter
    ]

    if not filtered:
        st.success("Žádné alerty pro vybraný filtr.")
    else:
        for alert in filtered:
            _render_alert_row(alert)

    # ── Audit trail ───────────────────────────────────────────────────────────
    with st.expander("🔍 EWS Audit Trail", expanded=False):
        audit_trail = result.get("audit_trail", [])
        if not audit_trail:
            st.info("Žádné audit záznamy.")
        else:
            for event in audit_trail:
                node = event.get("node", "")
                action = event.get("action", "")
                ts = event.get("timestamp", "")[:19].replace("T", " ")
                ph = event.get("prompt_hash")
                badge = "🤖 AI" if ph else "⚙️ DET"
                st.markdown(
                    f"<div class='audit-event {'ai' if ph else 'det'}'>"
                    f"<strong>{badge} {node}</strong> · {action} · <code>{ts}</code>"
                    + (f" · prompt_hash: <code>{ph}</code>" if ph else "")
                    + "</div>",
                    unsafe_allow_html=True,
                )

    # ── Run info ──────────────────────────────────────────────────────────────
    with st.expander("ℹ️ Run info", expanded=False):
        st.json({
            "run_id":       result.get("run_id"),
            "run_type":     result.get("run_type"),
            "triggered_at": result.get("triggered_at"),
            "status":       result.get("status"),
        })


def _render_alert_row(alert: dict) -> None:
    """Renderuje jeden alert řádek."""
    level = alert.get("alert_level", "GREEN")
    color = EW_COLORS.get(level, CITI_GRAY)
    icons = {"GREEN": "🟢", "AMBER": "🟡", "RED": "🔴"}
    icon = icons.get(level, "⚪")

    alert_type_labels = {
        "utilisation_spike": "Čerpání limitu",
        "dpd_increase":      "DPD",
        "covenant_breach":   "Kovenant",
        "revenue_drop":      "Pokles obratu",
        "overdraft_risk":    "Přečerpání",
        "tax_risk":          "Daňová compliance",
    }
    atype_label = alert_type_labels.get(alert.get("alert_type", ""), alert.get("alert_type", ""))

    with st.container():
        col_badge, col_info, col_vals = st.columns([1, 4, 3])

        with col_badge:
            st.markdown(
                f"<div style='text-align:center;padding:0.5rem'>"
                f"<span style='font-size:1.5rem'>{icon}</span><br>"
                f"<span style='font-size:0.7rem;font-weight:700;color:{color}'>{level}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

        with col_info:
            st.markdown(
                f"**{alert.get('company_name', '')}** · `{alert.get('ico', '')}`  \n"
                f"**{atype_label}** — {alert.get('description', '')}"
            )
            rec = alert.get("recommended_action", "")
            if rec:
                st.markdown(
                    f"<div style='font-size:0.82rem;color:#374151;margin-top:0.2rem'>"
                    f"💡 {rec}"
                    f"</div>",
                    unsafe_allow_html=True,
                )

        with col_vals:
            v1, v2, v3 = st.columns(3)
            with v1:
                st.metric("Hodnota", f"{alert.get('current_value', 0):.1f}")
            with v2:
                st.metric("Práh", f"{alert.get('threshold', 0):.1f}")
            with v3:
                dev = alert.get("deviation_pct", 0)
                st.metric("Odchylka", f"{dev:+.1f} %")

    st.markdown(
        "<hr style='border:none;border-top:1px solid #E5E7EB;margin:0.4rem 0'>",
        unsafe_allow_html=True,
    )
