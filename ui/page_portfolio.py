"""
Portfolio Dashboard — ui/page_portfolio.py
Přehled 6 klientů s Early Warning statusem, metrikami a akcemi.
"""

import streamlit as st

from ui.styles import (
    EW_COLORS,
    CITI_BLUE,
    ew_badge_html,
    fmt_czk,
    fmt_pct,
    wcr_icon,
)
from utils.data_connector import get_portfolio_clients
from utils.wcr_rules import WCR_LIMITS


@st.cache_data(ttl=300)
def _load_portfolio() -> list[dict]:
    return get_portfolio_clients()


def render_portfolio_page() -> None:
    """Renderuje Portfolio Dashboard stránku."""

    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,{CITI_BLUE} 0%,#0066CC 100%);
             color:white;padding:1.2rem 1.5rem;border-radius:10px;margin-bottom:1rem">
            <h2 style="margin:0;font-size:1.4rem">📊 Portfolio Dashboard</h2>
            <p style="margin:0.2rem 0 0;font-size:0.85rem;opacity:0.85">
                Kreditní portfolio · GenAI pro underwriting · Horizon Bank
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_title_spacer, col_refresh = st.columns([6, 1])
    with col_refresh:
        if st.button("🔄 Obnovit", key="refresh_portfolio", help="Vymazat cache a znovu načíst"):
            _load_portfolio.clear()
            st.rerun()

    portfolio = _load_portfolio()

    # ── Souhrnné KPI karty ─────────────────────────────────────────────────────
    ew_counts = {"GREEN": 0, "AMBER": 0, "RED": 0}
    breach_count = 0
    for c in portfolio:
        ew_counts[c.get("ew_alert_level", "GREEN")] = (
            ew_counts.get(c.get("ew_alert_level", "GREEN"), 0) + 1
        )
        if c.get("wcr_breaches"):
            breach_count += 1

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Klientů celkem", len(portfolio))
    with col2:
        st.metric("🟢 Green", ew_counts["GREEN"])
    with col3:
        st.metric("🟡 Amber", ew_counts["AMBER"])
    with col4:
        st.metric("🔴 Red (WCR breach)", breach_count)

    st.markdown("---")

    # ── Filtr Early Warning ────────────────────────────────────────────────────
    ew_filter = st.radio(
        "Filtr Early Warning",
        options=["Vše", "GREEN", "AMBER", "RED"],
        horizontal=True,
        index=0,
    )

    filtered = portfolio if ew_filter == "Vše" else [
        c for c in portfolio if c.get("ew_alert_level") == ew_filter
    ]

    # ── Early Warning System ───────────────────────────────────────────────────
    st.markdown("---")
    _render_early_warning_section()

    st.markdown("---")

    # ── Tabulka klientů ────────────────────────────────────────────────────────
    for client in filtered:
        _render_client_row(client)

    # ── Skills Library (sidebar collapsible) ───────────────────────────────────
    with st.expander("🧠 Skills Library (YAML versions)", expanded=False):
        _render_skills_library()


def _render_client_row(client: dict) -> None:
    """Renderuje jeden řádek klienta s expandovatelným detailem."""
    ico = client["ico"]
    name = client["company_name"]
    ew = client.get("ew_alert_level", "GREEN")
    ew_color = EW_COLORS.get(ew, "#6B7280")
    breaches = client.get("wcr_breaches", [])
    metrics = client.get("metrics", {})
    covenant = client.get("covenant_status", "OK")

    icons = {"GREEN": "🟢", "AMBER": "🟡", "RED": "🔴"}
    icon = icons.get(ew, "⚪")

    with st.container():
        col_info, col_metrics = st.columns([3, 5])

        with col_info:
            wcr_str = (
                f"<span style='color:#DC2626;font-size:0.8rem'>⚠️ {len(breaches)} WCR porušení</span>"
                if breaches else
                "<span style='color:#16A34A;font-size:0.8rem'>✅ WCR OK</span>"
            )
            st.markdown(
                f"**{name}**  \n"
                f"IČO: `{ico}` · {client.get('sector', '')}  \n"
                f"{icon} **{ew}** · Covenant: {covenant}  \n"
                f"CRIBIS: **{client.get('cribis_rating', 'N/A')}**",
            )
            st.markdown(wcr_str, unsafe_allow_html=True)

        with col_metrics:
            m1, m2, m3, m4 = st.columns(4)
            lev      = metrics.get("leverage_ratio") or None   # 0.0 → None (no data)
            dscr_val = metrics.get("dscr") or None             # 0.0 → None (no data)
            with m1:
                if lev is None:
                    st.metric("Leverage", "N/A")
                    st.caption("— bez CRIBIS dat")
                else:
                    ok = lev <= WCR_LIMITS["max_leverage_ratio"]
                    st.metric("Leverage", f"{lev}x")
                    st.caption(f"{wcr_icon(ok)} limit ≤5.0x")
            with m2:
                if dscr_val is None:
                    st.metric("DSCR", "N/A")
                    st.caption("— bez CRIBIS dat")
                else:
                    ok = dscr_val >= WCR_LIMITS["min_dscr"]
                    st.metric("DSCR", f"{dscr_val}")
                    st.caption(f"{wcr_icon(ok)} limit ≥1.2")
            with m3:
                ok = metrics.get("utilisation_pct", 0) <= WCR_LIMITS["max_utilisation_pct"]
                st.metric("Využití", fmt_pct(metrics.get("utilisation_pct")))
                st.caption(f"{wcr_icon(ok)} limit ≤85%")
            with m4:
                dpd = client.get("dpd_current", 0)
                ok = dpd <= WCR_LIMITS["max_dpd_days"]
                st.metric("DPD", f"{dpd} dní")
                st.caption(f"{wcr_icon(ok)} limit ≤30")

    # Expandovatelný detail s WCR breaches
    if breaches:
        with st.expander(f"⚠️ WCR porušení pro {name}", expanded=False):
            for b in breaches:
                st.warning(b)

    st.markdown(
        "<hr style='border:none;border-top:1px solid #E5E7EB;margin:0.5rem 0'>",
        unsafe_allow_html=True,
    )


def _render_early_warning_section() -> None:
    """Early Warning System — inline sekce pod portfoliem."""
    from ui.styles import EW_COLORS, CITI_GRAY

    st.markdown("### ⚠️ Early Warning System")

    col_run, col_type, col_spacer = st.columns([2, 2, 4])
    with col_run:
        run_ews = st.button("▶ Spustit EWS analýzu", type="primary",
                            use_container_width=True, key="run_ews_portfolio")
    with col_type:
        run_type = st.selectbox("Typ", ["on_demand", "daily_batch"],
                                key="ews_run_type", label_visibility="collapsed")

    if run_ews:
        with st.status("⏳ EWS pipeline běží...", expanded=True) as ews_status:
            st.write("📊 Načítám portfolio a metriky...")
            st.write("🔍 Detekuji anomálie (utilisation, DPD, overdraft, tax)...")
            st.write("⚠️ Generuji alerty...")
            try:
                from early_warning.graph import run_early_warning
                ews_result = run_early_warning(run_type)
                st.session_state["ews_result"] = ews_result
                ews_status.update(label="✅ EWS dokončeno", state="complete", expanded=False)
            except Exception as exc:
                ews_status.update(label="❌ EWS selhalo", state="error")
                st.error(f"EWS pipeline selhala: {exc}")

    ews_result = st.session_state.get("ews_result")
    if ews_result is None:
        st.info("Stiskněte **▶ Spustit EWS analýzu** pro detekci rizik v portfoliu.")
        return

    summary = ews_result.get("summary", {})
    alerts  = ews_result.get("alerts", [])

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Klientů analyzováno", summary.get("total_clients", 0))
    k2.metric("🔴 RED alerty", summary.get("red_alerts", 0))
    k3.metric("🟡 AMBER alerty", summary.get("amber_alerts", 0))
    k4.metric("Alertů celkem", len(alerts))

    if not alerts:
        st.success("✅ Žádné Early Warning alerty.")
        return

    level_filter = st.radio("Filtr alertů", ["Vše", "RED", "AMBER"],
                            horizontal=True, key="ews_filter_portfolio")
    filtered_alerts = alerts if level_filter == "Vše" else [
        a for a in alerts if a.get("alert_level") == level_filter
    ]

    alert_type_labels = {
        "utilisation_spike": "Čerpání limitu", "dpd_increase": "DPD",
        "covenant_breach":   "Kovenant",       "revenue_drop": "Pokles obratu",
        "overdraft_risk":    "Přečerpání",      "tax_risk":     "Daňová compliance",
    }
    icons = {"GREEN": "🟢", "AMBER": "🟡", "RED": "🔴"}

    with st.expander(f"Zobrazit {len(filtered_alerts)} alertů", expanded=True):
        for alert in filtered_alerts[:30]:
            level     = alert.get("alert_level", "GREEN")
            color     = EW_COLORS.get(level, CITI_GRAY)
            icon      = icons.get(level, "⚪")
            atype     = alert_type_labels.get(alert.get("alert_type", ""), alert.get("alert_type", ""))
            rec       = alert.get("recommended_action", "")

            col_badge, col_info, col_vals = st.columns([1, 5, 3])
            with col_badge:
                st.markdown(
                    f"<div style='text-align:center;padding:0.3rem'>"
                    f"<span style='font-size:1.3rem'>{icon}</span><br>"
                    f"<span style='font-size:0.7rem;font-weight:700;color:{color}'>{level}</span>"
                    f"</div>", unsafe_allow_html=True)
            with col_info:
                st.markdown(
                    f"**{alert.get('company_name', '')}** `{alert.get('ico', '')}`  \n"
                    f"**{atype}** — {alert.get('description', '')}"
                )
                if rec:
                    st.markdown(
                        f"<div style='font-size:0.82rem;color:#374151'>💡 {rec}</div>",
                        unsafe_allow_html=True)
            with col_vals:
                v1, v2 = st.columns(2)
                v1.metric("Hodnota", f"{alert.get('current_value', 0):.1f}")
                v2.metric("Práh", f"{alert.get('threshold', 0):.1f}")

            st.markdown(
                "<hr style='border:none;border-top:1px solid #E5E7EB;margin:0.3rem 0'>",
                unsafe_allow_html=True)


def _render_skills_library() -> None:
    """Renderuje tabulku skills pro audit purposes."""
    from skills import registry

    skills = registry.get_all_skills()
    if not skills:
        st.info("Žádné skills nenalezeny.")
        return

    for skill in skills:
        col1, col2, col3, col4 = st.columns([3, 1, 2, 3])
        with col1:
            st.markdown(f"**{skill['name']}** (`{skill['skill_key']}`)")
        with col2:
            st.markdown(f"v{skill['version']}")
        with col3:
            node_icon = "🤖" if skill.get("node_type") == "AI" else "⚙️"
            st.markdown(f"{node_icon} {skill.get('node_type', 'N/A')}")
        with col4:
            st.markdown(f"`hash:{skill['prompt_hash']}` · approved: {skill.get('approved_by', 'N/A')}")
