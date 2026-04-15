"""
Nastavení — ui/page_settings.py
WCR limity · EW prahy · Skills Library · Skills Management · Databricks status
"""
import os
import re

import streamlit as st

from ui.styles import ACCENT, TEXT_SEC
from utils.wcr_rules import WCR_LIMITS, EW_THRESHOLDS


def render_settings_page() -> None:
    """Renderuje stránku Nastavení."""

    st.markdown(
        f"""
        <div style="background:{ACCENT};color:white;padding:1.2rem 1.5rem;
             border-radius:10px;margin-bottom:1rem">
            <h2 style="margin:0;font-size:1.4rem">⚙️ Nastavení platformy</h2>
            <p style="margin:0.2rem 0 0;font-size:0.85rem;opacity:0.85">
                WCR limity · EW prahy · Skills Library · Skills Management · Databricks
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📏 WCR Limity",
        "⚠️ EW Prahy",
        "🧠 Skills Library",
        "➕ Správa Skills",
        "🗄️ Databricks",
    ])

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
            ("Využití — RED práh",     f"≥ {EW_THRESHOLDS['utilisation_red_pct']} %"),
            ("Využití — AMBER práh",   f"≥ {EW_THRESHOLDS['utilisation_amber_pct']} %"),
            ("DPD — RED práh",         f"≥ {EW_THRESHOLDS['dpd_red_days']} dní"),
            ("DPD — AMBER práh",       f"≥ {EW_THRESHOLDS['dpd_amber_days']} dní"),
            ("Pokles obratu — RED",    f"> {EW_THRESHOLDS['revenue_drop_red_pct']} % MoM"),
            ("Pokles obratu — AMBER",  f"> {EW_THRESHOLDS['revenue_drop_amber_pct']} % MoM"),
            ("Přečerpání — RED",       f"≥ {EW_THRESHOLDS['overdraft_red_pct']} % dní"),
            ("Přečerpání — AMBER",     f"≥ {EW_THRESHOLDS['overdraft_amber_pct']} % dní"),
            ("Tax compliance — AMBER", f"< {EW_THRESHOLDS['tax_compliance_amber']} %"),
            ("Covenant risk — RED",    f"≥ {EW_THRESHOLDS['covenant_risk_red']}"),
            ("Covenant risk — AMBER",  f"≥ {EW_THRESHOLDS['covenant_risk_amber']}"),
        ]

        col1, col2 = st.columns(2)
        for i, (label, val) in enumerate(thresholds):
            with (col1 if i % 2 == 0 else col2):
                st.text_input(label, value=val, disabled=True, key=f"ew_{i}")

    # ── Skills Library ─────────────────────────────────────────────────────────
    with tab3:
        _render_skills_library()

    # ── Skills Management ──────────────────────────────────────────────────────
    with tab4:
        _render_skills_management()

    # ── Databricks status ──────────────────────────────────────────────────────
    with tab5:
        _render_databricks_tab()


# ── Skills Library ─────────────────────────────────────────────────────────────

def _render_skills_library() -> None:
    st.markdown("### Skills Library")
    st.markdown(
        "YAML skill soubory s prompt verzemi a hashy. "
        "Každý skill je auditován a má neměnný `prompt_hash`."
    )
    st.markdown("---")

    try:
        from skills import registry
        skills = registry.get_all_skills()

        if not skills:
            st.info("Žádné skills nenalezeny.")
            return

        col_h1, col_h2, col_h3, col_h4 = st.columns([3, 1, 2, 3])
        col_h1.markdown("**Skill**")
        col_h2.markdown("**Verze**")
        col_h3.markdown("**Typ**")
        col_h4.markdown("**Hash / Schválil**")
        st.markdown(
            "<hr style='border:none;border-top:1px solid #E5E7EB;margin:0.3rem 0'>",
            unsafe_allow_html=True,
        )

        for skill in skills:
            node_icon = "🤖" if skill.get("node_type") == "AI" else "⚙️"
            with st.expander(
                f"{node_icon} **{skill['name']}** (`{skill['skill_key']}`) · v{skill['version']}",
                expanded=False,
            ):
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.markdown(f"**Typ:** {skill.get('node_type', 'N/A')}")
                    st.markdown(f"**Autor:** {skill.get('author', 'N/A')}")
                with c2:
                    st.markdown(f"**Schválil:** {skill.get('approved_by', 'N/A')}")
                    st.markdown(f"**Datum:** {skill.get('approved_at', 'N/A')}")
                with c3:
                    st.markdown(f"**Hash:** `{skill['prompt_hash']}`")

                constraints = skill.get("constraints", [])
                if constraints:
                    st.markdown("**Constraints:**")
                    for c in constraints:
                        st.markdown(f"  - {c}")

    except Exception as exc:
        st.error(f"Nelze načíst Skills: {exc}")


# ── Skills Management ──────────────────────────────────────────────────────────

def _render_skills_management() -> None:
    """
    Formulář pro přidání nového skill YAML.
    Libovolný tým může registrovat svůj extrakční/analytický agent.
    """
    from skills import registry

    st.markdown("### Správa Skills")
    st.markdown(
        "Chcete využít agentní architekturu Horizon Bank pro vlastní pipeline? "
        "Vyplňte formulář níže — systém vygeneruje skill YAML, zaregistruje ho a okamžitě ho "
        "zpřístupní pro spuštění v pipelines."
    )
    st.markdown("---")

    # ── Existující skills: smazat / zobrazit ───────────────────────────────────
    skills = registry.get_all_skills()
    custom_skills = [s for s in skills if s["skill_key"] not in {
        "extractor_skill", "maker_skill", "checker_skill",
        "esg_skill", "ew_analyzer_skill", "calculator_skill",
    }]

    if custom_skills:
        st.markdown("#### Vlastní (custom) skills")
        for s in custom_skills:
            c1, c2, c3 = st.columns([4, 2, 1])
            c1.markdown(f"**{s['name']}** (`{s['skill_key']}`) — v{s['version']} · {s.get('author', '—')}")
            node_icon = "🤖" if s.get("node_type") == "AI" else "⚙️"
            c2.markdown(f"{node_icon} {s.get('node_type', 'N/A')} · `{s['prompt_hash']}`")
            if c3.button("🗑️", key=f"del_{s['skill_key']}", help="Smazat skill"):
                registry.delete_skill(s["skill_key"])
                st.success(f"Skill `{s['skill_key']}` byl smazán.")
                st.rerun()

        st.markdown("---")

    # ── Formulář pro nový skill ────────────────────────────────────────────────
    st.markdown("#### Přidat nový skill")

    with st.form("add_skill_form", clear_on_submit=True):
        st.markdown("##### Identifikace")
        fc1, fc2 = st.columns(2)
        with fc1:
            skill_key = st.text_input(
                "Klíč souboru *",
                placeholder="my_team_extraction_skill",
                help="Jedinečný identifikátor (a-z, 0-9, _). Použije se jako název YAML souboru.",
            )
            skill_name = st.text_input(
                "Název skill *",
                placeholder="My Team Extraction Agent",
                help="Lidsky čitelný název zobrazovaný v UI.",
            )
        with fc2:
            skill_version = st.text_input("Verze *", value="1.0", placeholder="1.0")
            skill_author = st.text_input("Autor / tým", placeholder="tym_x")

        st.markdown("##### Konfigurace")
        fc3, fc4 = st.columns(2)
        with fc3:
            node_type = st.selectbox(
                "Typ uzlu *",
                options=["AI", "DETERMINISTIC"],
                help="AI = volá Claude API. DETERMINISTIC = čistý Python, žádný LLM.",
            )
            language = st.selectbox("Jazyk promptu", options=["cs", "en", "sk"])
        with fc4:
            approved_by = st.text_input("Schválil", placeholder="risk_mgmt")
            import datetime
            approved_at = st.date_input("Datum schválení", value=datetime.date.today())

        st.markdown("##### Prompt")
        prompt_text = st.text_area(
            "Prompt text *",
            height=220,
            placeholder=(
                "Jsi extrakční agent pro tým X. Tvůj úkol je...\n\n"
                "PRAVIDLA:\n"
                "1. NIKDY nepočítej matematiku — použij předem vypočtené hodnoty.\n"
                "2. Každé číslo musí mít [CITATION:source_id].\n"
                "..."
            ),
            help="Celý text systémového promptu. Bude uložen do YAML a auditován sha256 hashem.",
        )

        st.markdown("##### Constraints (volitelné)")
        constraints_raw = st.text_area(
            "Jeden constraint na řádek",
            height=100,
            placeholder=(
                "NIKDY nepočítej matematiku\n"
                "Každé číslo musí mít [CITATION:source_id]\n"
                "Nezmiňuj interní klientská data mimo pipeline"
            ),
        )

        st.markdown("##### Data sources (volitelné)")
        data_sources_raw = st.text_area(
            "Jeden source_id na řádek",
            height=80,
            placeholder="company_master\nfin_profile\ncustom_source_x",
        )

        submitted = st.form_submit_button("💾 Uložit skill a zaregistrovat", type="primary", use_container_width=True)

    if submitted:
        # Validace
        errors = []
        if not skill_key.strip():
            errors.append("Klíč souboru je povinný.")
        elif not re.match(r"^[a-z0-9_]+$", skill_key.strip()):
            errors.append("Klíč souboru smí obsahovat pouze a-z, 0-9 a _.")
        if not skill_name.strip():
            errors.append("Název skill je povinný.")
        if not skill_version.strip():
            errors.append("Verze je povinná.")
        if not prompt_text.strip():
            errors.append("Prompt text je povinný.")

        if errors:
            for e in errors:
                st.error(e)
        else:
            constraints_list = [
                line.strip() for line in constraints_raw.splitlines() if line.strip()
            ]
            data_sources_list = [
                line.strip() for line in data_sources_raw.splitlines() if line.strip()
            ]

            skill_data = {
                "name":                skill_name.strip(),
                "version":             skill_version.strip(),
                "author":              skill_author.strip() or "custom_team",
                "approved_by":         approved_by.strip() or "pending",
                "approved_at":         str(approved_at),
                "node_type":           node_type,
                "language":            language,
                "constraints":         constraints_list,
                "data_sources_required": data_sources_list,
                "prompt":              prompt_text.strip(),
            }

            try:
                saved_path = registry.save_skill(skill_key.strip(), skill_data)
                import hashlib
                ph = hashlib.sha256(prompt_text.strip().encode()).hexdigest()[:12]
                st.success(
                    f"Skill **{skill_name}** (`{skill_key}`) uložen.  \n"
                    f"Soubor: `{saved_path.name}` · Prompt hash: `{ph}`  \n"
                    f"Skill je ihned dostupný v Skills Library a pro spuštění v pipelinech."
                )
                st.rerun()
            except Exception as exc:
                st.error(f"Chyba při ukládání: {exc}")

    # ── Jak použít skill ────────────────────────────────────────────────────────
    with st.expander("ℹ️ Jak zaregistrovaný skill spustit v pipeline?", expanded=False):
        st.markdown(
            """
**1. Přímé volání v Python kódu:**
```python
from skills import registry

skill = registry.get("my_team_extraction_skill")
prompt = skill["prompt"]
# → předej do anthropic.Anthropic().messages.create(...)
```

**2. Použití v LangGraph uzlu (AI node):**
```python
from skills import registry
from utils.audit import _audit

def my_team_node(state: AgentState) -> AgentState:
    skill = registry.get("my_team_extraction_skill")
    # AI: volá Claude API
    response = client.messages.create(
        model="claude-opus-4-6",
        system=skill["prompt"],
        messages=[{"role": "user", "content": state["case_view_json"]}],
    )
    _audit(state, "my_team_node", prompt=skill["prompt"], detail="extraction done")
    return {**state, "my_result": response.content[0].text}
```

**3. ESG-style dispatcher pipeline:**
```python
from esg_pipeline.dispatcher import run_esg_pipeline
# Nebo si napište vlastní graph.py podle vzoru early_warning/graph.py
```

Skill YAML soubor je uložen v `skills/<klíč>.yaml` a automaticky ho načte `SkillsRegistry`.
"""
        )


# ── Databricks tab ─────────────────────────────────────────────────────────────

def _render_databricks_tab() -> None:
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
        host     = os.getenv("DATABRICKS_HOST", "—")
        http_path = os.getenv("DATABRICKS_HTTP_PATH", "—")
        catalog  = os.getenv("DATABRICKS_CATALOG", "vse_banka")
        schema   = os.getenv("DATABRICKS_SCHEMA_SILVER", "obsluha_klienta")
        st.text_input("Host", value=host[:40] + "…" if len(host) > 40 else host, disabled=True, key="db_host")
        st.text_input("HTTP Path", value=http_path, disabled=True, key="db_path")
        st.text_input("Catalog", value=catalog, disabled=True, key="db_cat")
        st.text_input("Schema Silver", value=schema, disabled=True, key="db_sch")

    with col2:
        st.markdown("**Silver tabulky:**")
        tables = [
            ("silver_company_master",              "Základní info firmy (IČO STRING)"),
            ("silver_corporate_customer",          "Bridge — customer_id (IČO INT)"),
            ("silver_corporate_financial_profile", "Finanční profil (SCD Type 2)"),
            ("silver_credit_history",              "Kreditní historie, DPD, kovenanty"),
            ("silver_transactions",                "Měsíční transakce 12M"),
            ("silver_client_incidents",            "CRM incidenty 24M"),
        ]
        for tbl, desc in tables:
            st.markdown(
                f"<div style='font-size:0.82rem;padding:0.2rem 0'>"
                f"<code>{tbl}</code><br>"
                f"<span style='color:{TEXT_SEC}'>{desc}</span>"
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

    # ── Live CRIBIS diagnostika ────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 🔬 Diagnostika CRIBIS připojení")
    st.markdown(
        "Testuje JOIN Silver IČO → CRIBIS `ic` sloupec. "
        "Hlavní příčina N/A metrik: CRIBIS `ic` je číslo bez vedoucích nul, "
        "Silver IČO je string s vedoucími nulami."
    )

    diag_ico = st.text_input(
        "IČO pro test (z portfolia)",
        value="45274649",
        key="diag_ico_input",
        help="Zadej IČO firmy z portfolia. Uvidíš, co CRIBIS vrátí."
    )
    if st.button("▶ Spustit CRIBIS test", key="run_cribis_diag"):
        if is_demo:
            st.warning("Demo mode — Databricks se nevolá. Přepni ICM_ENV=production.")
        else:
            cat_cr = os.getenv("DATABRICKS_CATALOG_CRIBIS", "vse_banka")
            sch_cr = os.getenv("DATABRICKS_SCHEMA_CRIBIS", "investment_banking")
            from utils.data_connector import query, _norm_ico
            try:
                # Test 1: ukáž raw ic hodnoty pro toto IČO
                raw = query(f"""
                    SELECT CAST(ic AS STRING) AS ic_raw,
                           CAST(TRY_CAST(ic AS BIGINT) AS STRING) AS ic_norm,
                           nazev_subjektu, obdobi_do
                    FROM {cat_cr}.{sch_cr}.silver_data_cribis_v3
                    WHERE CAST(TRY_CAST(ic AS BIGINT) AS STRING) = '{_norm_ico(diag_ico)}'
                    ORDER BY obdobi_do DESC
                    LIMIT 3
                """)
                if raw:
                    st.success(f"✅ CRIBIS vrátil {len(raw)} záznam(ů) pro IČO `{diag_ico}`")
                    for r in raw:
                        st.markdown(
                            f"- `ic_raw`=**{r['ic_raw']}** · `ic_norm`=**{r['ic_norm']}** · "
                            f"firma: **{r.get('nazev_subjektu', '—')}** · "
                            f"období do: **{r.get('obdobi_do', '—')}**"
                        )

                    # Test 2: ukáž metriky
                    from utils.data_connector import get_cribis_data
                    cribis = get_cribis_data(diag_ico)
                    if cribis:
                        st.markdown("**Vypočtené metriky:**")
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Leverage", f"{cribis.get('leverage_ratio', 'N/A')}x")
                        c2.metric("DSCR", f"{cribis.get('dscr', 'N/A')}")
                        c3.metric("Current Ratio", f"{cribis.get('current_ratio', 'N/A')}")
                else:
                    # Diagnostika proč nesedí
                    sample = query(f"""
                        SELECT CAST(ic AS STRING) AS ic_raw,
                               CAST(TRY_CAST(ic AS BIGINT) AS STRING) AS ic_norm,
                               nazev_subjektu
                        FROM {cat_cr}.{sch_cr}.silver_data_cribis_v3
                        LIMIT 5
                    """)
                    st.error(f"❌ Žádný záznam pro IČO `{diag_ico}` (normalizováno: `{_norm_ico(diag_ico)}`).")
                    st.markdown("**Ukázka prvních 5 `ic` hodnot v CRIBIS:**")
                    for r in sample:
                        st.markdown(f"- raw=`{r['ic_raw']}` · norm=`{r['ic_norm']}` · {r.get('nazev_subjektu','')}")
            except Exception as exc:
                st.error(f"Chyba při dotazu: {exc}")

    st.markdown("---")
    with st.expander("📐 Systémová architektura", expanded=False):
        import base64, pathlib as _pl
        _static = _pl.Path(__file__).parent.parent / "static"

        _arc_path = _static / "architecture_v5.jpg"
        if _arc_path.exists():
            _arc_b64 = base64.b64encode(_arc_path.read_bytes()).decode()
            st.markdown("**Agentní architektura**")
            st.markdown(
                f'<img src="data:image/jpeg;base64,{_arc_b64}" style="width:100%;border-radius:8px;margin-bottom:1rem">',
                unsafe_allow_html=True,
            )

        _lin_path = _static / "data_lineage_v3.jpg"
        if _lin_path.exists():
            _lin_b64 = base64.b64encode(_lin_path.read_bytes()).decode()
            st.markdown("**Data Lineage & Platform Architecture**")
            st.markdown(
                f'<img src="data:image/jpeg;base64,{_lin_b64}" style="width:100%;border-radius:8px;margin-bottom:1rem">',
                unsafe_allow_html=True,
            )

        st.markdown("**Gap analýza: Diagram vs. Implementace**")
        st.markdown(
            "| Vrstva | Status | Gap |\n"
            "|--------|--------|-----|\n"
            "| Bronze Layer / Data Lake | ❌ | Kód jde přímo na Silver, žádná raw vrstva |\n"
            "| Quarantine Zone | ❌ | Pouze FROZEN status, bez karanténního workflow |\n"
            "| Helios / SharePoint downstream | ❌ | Memo pouze v Streamlit, žádný export |\n"
            "| CMP / CBS / CRM upstream | ❌ | Nejsou v data_connector.py |\n"
            "| ESG Datamart prod write | ⚠️ | dispatcher.py má TODO pro INSERT |\n"
            "| EWS Delta write + notifikace | ⚠️ | alert_dispatcher.py má TODO |\n"
            "| PII Masking (Silver ingest) | ⚠️ | GDPR sanitize je až po approval |\n"
            "| Silver Layer (Databricks) | ✅ | Single source of truth |\n"
            "| Case View + LLM Draft | ✅ | phase2 + phase3 |\n"
            "| 4-Eyes Rule (Human Review) | ✅ | phase4 |\n"
            "| Immutable Audit Trail | ✅ | utils/audit.py |\n"
            "| CRIBIS + Justice + ARES fallback | ✅ | data_fetcher.py cascade |\n"
            "| ESG pipeline architektura | ✅ | collector→transformer→dispatcher |\n"
            "| EWS portfolio monitoring | ✅ | early_warning/ DP2 pipeline |\n"
        )

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
