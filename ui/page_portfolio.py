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
from utils.mock_data import get_portfolio
from utils.wcr_rules import WCR_LIMITS


def render_portfolio_page() -> None:
    """Renderuje Portfolio Dashboard stránku."""

    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,{CITI_BLUE} 0%,#0066CC 100%);
             color:white;padding:1.2rem 1.5rem;border-radius:10px;margin-bottom:1rem">
            <h2 style="margin:0;font-size:1.4rem">📊 Portfolio Dashboard</h2>
            <p style="margin:0.2rem 0 0;font-size:0.85rem;opacity:0.85">
                Kreditní portfolio — 6 klientů · ICM GenAI Platform · Tým 7
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    portfolio = get_portfolio()

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
        col_info, col_metrics, col_action = st.columns([3, 4, 2])

        with col_info:
            st.markdown(
                f"**{name}**  \n"
                f"IČO: `{ico}` · {client.get('sector', '')}  \n"
                f"{icon} **{ew}** · Covenant: {covenant}  \n"
                f"CRIBIS: **{client.get('cribis_rating', 'N/A')}**"
            )

        with col_metrics:
            m1, m2, m3, m4 = st.columns(4)
            with m1:
                ok = metrics.get("leverage_ratio", 0) <= WCR_LIMITS["max_leverage_ratio"]
                st.metric("Leverage", f"{metrics.get('leverage_ratio', 'N/A')}x", delta=None)
                st.caption(f"{wcr_icon(ok)} limit ≤5.0x")
            with m2:
                ok = metrics.get("dscr", 0) >= WCR_LIMITS["min_dscr"]
                st.metric("DSCR", f"{metrics.get('dscr', 'N/A')}", delta=None)
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

        with col_action:
            if st.button("📄 Generovat memo", key=f"gen_{ico}", type="primary"):
                st.session_state["selected_ico"] = ico
                st.session_state["page"] = "credit_memo"
                st.rerun()

            if breaches:
                st.markdown(
                    f"<span style='color:#DC2626;font-size:0.8rem'>"
                    f"⚠️ {len(breaches)} WCR porušení</span>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    "<span style='color:#16A34A;font-size:0.8rem'>✅ WCR OK</span>",
                    unsafe_allow_html=True,
                )

    # Expandovatelný detail s WCR breaches
    if breaches:
        with st.expander(f"⚠️ WCR porušení pro {name}", expanded=False):
            for b in breaches:
                st.warning(b)

    st.markdown(
        "<hr style='border:none;border-top:1px solid #E5E7EB;margin:0.5rem 0'>",
        unsafe_allow_html=True,
    )


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
