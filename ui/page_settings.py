"""
Nastavení — ui/page_settings.py
WCR limity, EW prahy, Skills Library, Databricks status.
"""
import os

import streamlit as st

from ui.styles import CITI_BLUE, CITI_GRAY
from utils.wcr_rules import WCR_LIMITS, EW_THRESHOLDS


def render_settings_page() -> None:
    """Renderuje stránku Nastavení."""

    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,{CITI_BLUE} 0%,#0066CC 100%);
             color:white;padding:1.2rem 1.5rem;border-radius:10px;margin-bottom:1rem">
            <h2 style="margin:0;font-size:1.4rem">⚙️ Nastavení platformy</h2>
            <p style="margin:0.2rem 0 0;font-size:0.85rem;opacity:0.85">
                WCR limity · EW prahy · Skills Library · Databricks status
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab1, tab2, tab3, tab4 = st.tabs(["📏 WCR Limity", "⚠️ EW Prahy", "🧠 Skills Library", "🗄️ Databricks"])

    # ── WCR limity ─────────────────────────────────────────────────────────────
    with tab1:
        st.markdown("### WCR Limity (Risk Management schváleno)")
        st.info("Tyto limity jsou schváleny Risk Management. Změna vyžaduje formální proces.")
        st.markdown("---")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Leverage Ratio (Net Debt/EBITDA)**")
            st.text_input("Max leverage", value=f"≤ {WCR_LIMITS['max_leverage_ratio']}x", disabled=True, key="wcr_lev")

            st.markdown("**DSCR (Op. CF / Debt Service)**")
            st.text_input("Min DSCR", value=f"≥ {WCR_LIMITS['min_dscr']}", disabled=True, key="wcr_dscr")

            st.markdown("**Využití limitu**")
            st.text_input("Max utilisation", value=f"≤ {WCR_LIMITS['max_utilisation_pct']} %", disabled=True, key="wcr_util")

        with col2:
            st.markdown("**Current Ratio (CA / CL)**")
            st.text_input("Min current ratio", value=f"≥ {WCR_LIMITS['min_current_ratio']}", disabled=True, key="wcr_cr")

            st.markdown("**DPD (Days Past Due)**")
            st.text_input("Max DPD", value=f"≤ {WCR_LIMITS['max_dpd_days']} dní", disabled=True, key="wcr_dpd")

        st.markdown("---")
        st.markdown(
            "<div style='font-size:0.8rem;color:#6B7280'>"
            "ℹ️ Leverage a DSCR jsou dostupné ze CRIBIS (Tým 8). "
            "Utilisation a DPD jsou ze Silver tabulek (vždy dostupné)."
            "</div>",
            unsafe_allow_html=True,
        )

    # ── EW prahy ───────────────────────────────────────────────────────────────
    with tab2:
        st.markdown("### Early Warning System prahy")
        st.info("DETERMINISTIC pravidla — LLM tato čísla nepočítá ani nemodifikuje.")
        st.markdown("---")

        thresholds = [
            ("Využití — RED práh",  f"≥ {EW_THRESHOLDS['utilisation_red_pct']} %"),
            ("Využití — AMBER práh", f"≥ {EW_THRESHOLDS['utilisation_amber_pct']} %"),
            ("DPD — RED práh",       f"≥ {EW_THRESHOLDS['dpd_red_days']} dní"),
            ("DPD — AMBER práh",     f"≥ {EW_THRESHOLDS['dpd_amber_days']} dní"),
            ("Pokles obratu — RED",  f"> {EW_THRESHOLDS['revenue_drop_red_pct']} % MoM"),
            ("Pokles obratu — AMBER", f"> {EW_THRESHOLDS['revenue_drop_amber_pct']} % MoM"),
            ("Přečerpání — RED",     f"≥ {EW_THRESHOLDS['overdraft_red_pct']} % dní"),
            ("Přečerpání — AMBER",   f"≥ {EW_THRESHOLDS['overdraft_amber_pct']} % dní"),
            ("Tax compliance — AMBER", f"< {EW_THRESHOLDS['tax_compliance_amber']} %"),
            ("Covenant risk — RED",  f"≥ {EW_THRESHOLDS['covenant_risk_red']}"),
            ("Covenant risk — AMBER", f"≥ {EW_THRESHOLDS['covenant_risk_amber']}"),
        ]

        col1, col2 = st.columns(2)
        for i, (label, val) in enumerate(thresholds):
            with (col1 if i % 2 == 0 else col2):
                st.text_input(label, value=val, disabled=True, key=f"ew_{i}")

    # ── Skills Library ─────────────────────────────────────────────────────────
    with tab3:
        st.markdown("### Skills Library")
        st.markdown("YAML skill soubory s prompt verzemi a hashy pro audit trail.")
        st.markdown("---")

        try:
            from skills import registry
            skills = registry.get_all_skills()

            for skill in skills:
                node_icon = "🤖" if skill.get("node_type") == "AI" else "⚙️"
                with st.expander(
                    f"{node_icon} **{skill['name']}** · v{skill['version']} · hash `{skill['prompt_hash']}`",
                    expanded=False,
                ):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.markdown(f"**Typ:** {skill.get('node_type', 'N/A')}")
                        st.markdown(f"**Autor:** {skill.get('author', 'N/A')}")
                    with col2:
                        st.markdown(f"**Schválil:** {skill.get('approved_by', 'N/A')}")
                        st.markdown(f"**Datum:** {skill.get('approved_at', 'N/A')}")
                    with col3:
                        st.markdown(f"**Hash:** `{skill['prompt_hash']}`")
                        st.markdown(f"**Verze:** `{skill['version']}`")

                    constraints = skill.get("constraints", [])
                    if constraints:
                        st.markdown("**Constraints:**")
                        for c in constraints:
                            st.markdown(f"  - {c}")
        except Exception as exc:
            st.error(f"Nelze načíst Skills: {exc}")

    # ── Databricks status ──────────────────────────────────────────────────────
    with tab4:
        st.markdown("### Databricks připojení")
        st.markdown("---")

        icm_env = os.getenv("ICM_ENV", "demo").lower()
        is_demo = icm_env != "production"

        if is_demo:
            st.warning("🟡 **Demo mode** — mock data, Databricks se nevolá")
        else:
            st.success("🟢 **Production mode** — reálná Databricks data")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Konfigurace:**")
            host = os.getenv("DATABRICKS_HOST", "—")
            http_path = os.getenv("DATABRICKS_HTTP_PATH", "—")
            catalog = os.getenv("DATABRICKS_CATALOG", "vse_banka")
            schema = os.getenv("DATABRICKS_SCHEMA_SILVER", "obsluha_klienta")
            st.text_input("Host", value=host[:40] + "…" if len(host) > 40 else host, disabled=True, key="db_host")
            st.text_input("HTTP Path", value=http_path, disabled=True, key="db_path")
            st.text_input("Catalog", value=catalog, disabled=True, key="db_cat")
            st.text_input("Schema Silver", value=schema, disabled=True, key="db_sch")

        with col2:
            st.markdown("**Silver tabulky:**")
            tables = [
                ("silver_company_master", "Základní info firmy (IČO STRING)"),
                ("silver_corporate_customer", "Bridge — customer_id (IČO INT)"),
                ("silver_corporate_financial_profile", "Finanční profil (SCD Type 2)"),
                ("silver_credit_history", "Kreditní historie, DPD, kovenanty"),
                ("silver_transactions", "Měsíční transakce 12M"),
                ("silver_client_incidents", "CRM incidenty 24M"),
            ]
            for tbl, desc in tables:
                st.markdown(
                    f"<div style='font-size:0.82rem;padding:0.2rem 0'>"
                    f"<code>{tbl}</code><br>"
                    f"<span style='color:{CITI_GRAY}'>{desc}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

        st.markdown("---")
        st.markdown("**CRIBIS (Tým 8):**")
        st.markdown(
            "`vse_banka.investment_banking.silver_data_cribis_v3`  \n"
            "Klíč: `ic` (VARCHAR) — JOIN přes `CAST(ic AS STRING) = ico`  \n"
            "Poskytuje: EBITDA, Leverage, DSCR (proxy), Current Ratio, YoY trendy"
        )

        st.markdown("**ESG / Flood data:**")
        st.markdown(
            "`vse_banka.icm_gen_ai.silver_ruian_buildings`  \n"
            "`vse_banka.icm_gen_ai.silver_building_flood_join`  \n"
            "Flood risk určen podle `company_master.city` → flood zóny Q5/Q20/Q100"
        )

        # Architektura
        st.markdown("---")
        with st.expander("📐 Systémová architektura", expanded=False):
            st.code("""
Upstream → Bronze → Silver ─────────────────────────────┐
             (DQ)   (clean)                              │
                      │                                  │
                 Quarantine Zone                         │
                                                         ▼
ESG Pipeline ──→ Cross-Domain      DP1: Credit Memo Pipeline
(pro Tým 5)      Datamart Tým5     Phase1→Phase2→Phase3→Phase4
                                    ↑ Skills Library (YAML)
                                   DP2: Early Warning System
                                   Portfolio→Metrics→Anomaly→Alerts
                                          │
                                          ▼
                                   Risk Management (Helios)
""", language="text")
