# GenAI pro underwriting — Horizon Bank · CLAUDE.md
## Developer Context for Claude Code

---

## Projekt

**GenAI pro underwriting** je AI-asistovaný systém pro kreditní analýzu firemních klientů Horizon Bank.
LangGraph + Claude/GPT-4o + Streamlit + Databricks Silver.

Diagramy: `static/architecture_v5.jpg` · `static/data_lineage_v3.jpg`

---

## Architektura souborů

```
app.py                              ← Streamlit entry point
static/
  horizon_logo.png                  ← Logo (base64-embedded v sidebar)
  architecture_v5.jpg               ← Architektura pro README/prezentace

pipeline/
  state.py                          ← AgentState, ProcessStatus (TypedDict)
  graph.py                          ← LangGraph StateGraph (build_graph, run_pipeline)
  routing.py                        ← Podmíněné hrany (DETERMINISTIC)
  nodes/
    phase1_extraction.py            ← AI: DataExtractorAgent + DET: ExtractionValidator
    phase2_analysis.py              ← DET: ContextBuilder + CreditAnalysisService (→ calculator.py)
    phase3_maker_checker.py         ← AI: MemoPreparationAgent, QualityControlChecker
                                      DET: PolicyRulesEngine (WCR check, skipped rules pro None)
    phase4_human_audit.py           ← DET: HumanReviewNode + RecordHumanDecision + GDPR sanitize

early_warning/
  graph.py                          ← EWS LangGraph pipeline (DP2)
  state.py                          ← EWState TypedDict
  nodes/
    portfolio_loader.py             ← DET: načte ACTIVE klienty + CRIBIS enrichment
    metrics_calculator.py           ← DET: utilisation, DPD, overdraft, tax compliance
    anomaly_detector.py             ← DET: pravidla + AI text recommended_action + News signály
    alert_generator.py              ← DET: sestaví alerts pro UI
    alert_dispatcher.py             ← DET: dispatch do Risk Management

esg_pipeline/
  collector.py                      ← flood risk, ESG score raw
  transformer.py                    ← AI: ESGTransformerAgent
  dispatcher.py                     ← DET: INSERT do esg_cross_domain_datamart (Tým 5)

skills/
  __init__.py                       ← SkillsRegistry singleton
                                      .get(name), .get_prompt_hash(name)
                                      .save_skill(key, data) → zapíše YAML, invaliduje cache
                                      .delete_skill(key) → smaže YAML + cache
                                      .get_all_skills() → seznam pro UI
  extractor_skill.yaml              ← DataExtractor v2.3
  maker_skill.yaml                  ← MemoPreparation v3.2
  checker_skill.yaml                ← QualityControl v2.0
  esg_skill.yaml                    ← ESGAnalysis v1.5
  esg_transformer_skill.yaml        ← ESGTransformer
  ew_analyzer_skill.yaml            ← EWS AI recommended_action
  calculator_skill.yaml             ← Formula docs (node_type: DETERMINISTIC)

utils/
  wcr_rules.py                      ← WCR_LIMITS, WCR_WARNINGS, WCR_BENCHMARKS,
                                      EW_THRESHOLDS, MIN_CITATION_COVERAGE=0.90,
                                      MAX_MAKER_ITERATIONS=3, API_RETRY_COUNT=3
                                      check_wcr_breaches(), build_wcr_report()
  calculator.py                     ← compute_all_metrics(cribis, internal, cribis_prev)
                                      calc_dscr, calc_capex, calc_leverage, calc_icr atd.
  data_connector.py                 ← Databricks Silver + CRIBIS + flood
                                      _norm_ico(ico) — KRITICKÁ funkce pro CRIBIS JOIN
                                      get_portfolio_clients() — 3 batch queries
                                      get_client_info(ico) — single-client
                                      get_cribis_data(ico), get_cribis_prev_period(ico)
  data_fetcher.py                   ← fetch_financial_data(ico) → FetchResult
                                      Fallback: CRIBIS → Justice.cz PDF → ARES API → Freeze
  news_fetcher.py                   ← EWS signály: ISIR insolvence, ČNB sazba, Google News
  audit.py                          ← _audit(state, node, action, result, prompt, ...)
                                      → immutable append-only, sha256[:12] pro AI uzly
  llm_factory.py                    ← get_llm() → LLMClient(provider, model)
                                      provider: anthropic | openai
                                      Výchozí: claude-opus-4-6 / gpt-4o
  mock_data.py                      ← 6 mock klientů, _mock_cribis(), _mock_cribis_prev()
                                      get_portfolio(), get_client(ico), get_mock_agent_result()
  chunking.py                       ← semantic_chunk() — dělení dokumentů

ui/
  styles.py                         ← Manrope font, ACCENT=#4D25EB, TEXT_MAIN=#0B0F17
                                      GLOBAL_CSS, page_header(), ew_badge_html(),
                                      status_badge_html(), fmt_czk(), fmt_pct()
  page_portfolio.py                 ← Portfolio Dashboard
                                      · EWS sekce NAHOŘE (před listem klientů)
                                      · Bez "Generovat memo" tlačítka v řádcích
                                      · _load_portfolio() cache + Obnovit button
  page_credit_memo.py               ← Credit Memo Generator
                                      · Vyhledávání klienta (text input)
                                      · Pipeline progress (st.status s 5 fázemi)
                                      · _render_wcr_tab() — skipped=⏭️, False=❌, None=⏭️
                                      · _render_metrics_tab() — Silver + CRIBIS raw data
                                      · _render_human_decision_panel() — Approve/Podmínečně/Reject
                                      · cases_log tracking v session_state
  page_human_review.py              ← 4-Eyes Rule Human Review
                                      · WCR rendering opraveno (skipped ≠ breach)
  page_cases_log.py                 ← Log zpracovaných cases (session_state["cases_log"])
                                      · KPI: total/approved/rejected/pending/wcr_fail
                                      · Filter + search
  page_settings.py                  ← 5 tabů:
                                      1. WCR Limity (read-only)
                                      2. EW Prahy (read-only)
                                      3. Skills Library (expander per skill)
                                      4. Správa Skills (formulář pro nový YAML skill)
                                      5. Databricks (config + silver tables + CRIBIS test)
  page_audit_trail.py               ← (legacy) standalone audit trail
  page_early_warning.py             ← (legacy) standalone EWS dashboard
```

---

## Klíčová pravidla (NIKDY neporušovat)

### 1. Deterministika vs. AI

- `# DETERMINISTIC` — čistý Python, žádný LLM
- `# AI` — volá Claude/GPT přes `utils/llm_factory.py`
- **LLM NIKDY nepočítá matematiku** — veškeré metriky přes `utils/calculator.py`
- `compute_all_metrics(cribis, internal, cribis_prev)` je jediný vstupní bod

### 2. Audit Trail

- `_audit()` z `utils/audit.py` musí být voláno v každém uzlu
- Audit trail je **append-only** — nikdy nepřepisuj existující eventy
- AI uzly: `prompt=skill["prompt"]` → automaticky se hashuje sha256[:12]
- DET uzly: `prompt=None` → `prompt_hash=None` v logu

### 3. API Failure → Process Freeze

- Při selhání Claude/GPT API: `status = ProcessStatus.FROZEN`
- **NIKDY** nefallbackuj na T-1 data nebo staré výsledky
- Max pokusy: `API_RETRY_COUNT = 3`, čekání: `API_RETRY_DELAY_SEC = 30`

### 4. Maker-Checker Loop

- Max iterace: `MAX_MAKER_ITERATIONS = 3` (guard v `wcr_rules.py`)
- Při překročení: `status = ProcessStatus.ESCALATED`
- Checker kontroluje POUZE citace a halucinace — NE matematiku ani WCR

### 5. Citations

- `MIN_CITATION_COVERAGE = 0.90` — 90 % čísel musí mít `[CITATION:source_id]`
- Povolené `source_id` jsou POUZE ty z `case_view["data_sources"]`

### 6. GDPR

- Klientská data jsou transient — neukládat persistentně
- Po schválení: `_sanitize_transient_data()` v `phase4_human_audit.py` vyčistí
  `extraction_result`, `case_view`, `draft_memo`, `financial_metrics`
- Audit trail zůstává — neobsahuje raw finanční data

### 7. Data Sources & Fallback

- Primární: CRIBIS (`vse_banka.investment_banking.silver_data_cribis_v3`)
- **CRIBIS klíč: `ic` (NUMERIC)** — viz bod 8 níže
- Fallback: CRIBIS → Justice.cz PDF → ARES API → Process Freeze
- CRIBIS prev period: `get_cribis_prev_period(ico)` — `ORDER BY obdobi_do DESC LIMIT 1 OFFSET 1`

### 8. CRIBIS IČO normalizace — KRITICKÉ

```
PROBLÉM:
  Silver silver_company_master.ico = STRING s vedoucími nulami: '00514152'
  CRIBIS ic = NUMERIC typ → CAST(ic AS STRING) = '514152' (bez nul)
  → přímý WHERE CAST(ic AS STRING) = '00514152' SELŽE (0 řádků)

ŘEŠENÍ:
  WHERE CAST(TRY_CAST(ic AS BIGINT) AS STRING) = '{_norm_ico(ico)}'

  _norm_ico(ico) v utils/data_connector.py:
      def _norm_ico(ico): return str(int(str(ico)))
      '00514152' → '514152'  ✓
      '27082440' → '27082440' ✓

PLATÍ PRO:
  · get_cribis_data(ico)       — single query
  · get_cribis_prev_period(ico) — single query
  · get_portfolio_clients()    — batch query (ico_list_norm)
  · cribis_map.get(_norm_ico(ico), {}) — Python-side lookup
```

### 9. DSCR vzorec (CAPEX-adjusted)

```
DSCR = (EBITDA - CAPEX - Taxes) / (Interest + bank_liabilities_st / 12)
CAPEX = max(0, fixed_assets_curr - fixed_assets_prev) + odpisy
       → pokud prev chybí: CAPEX_proxy = odpisy (konzervativnější)
       
odpisy sloupec v CRIBIS:
  upravy_hodnot_dlouhodobeho_hmotneho_a_nehmotneho_majetku_trvale
  (NE zkrácené 'odpisy' — sloupec neexistuje)
```

### 10. WCR skipped ≠ breach

```
Metriky Leverage, DSCR, Current Ratio závisí na CRIBIS.
Pokud CRIBIS data nejsou dostupná → hodnota = None.

V policy_rules_engine:
  passed = None  → skipped = True  (⏭️ Čeká na CRIBIS data)
  passed = False → breach          (❌ porušeno)
  passed = True  → OK              (✅ splněno)

Počítadla:
  passed_rules  = sum(r["passed"] is True)
  failed_rules  = sum(r["passed"] is False)
  skipped = sum(r["skipped"])   ← zobrazit zvlášť v UI
```

---

## Branding

```
Název produktu:  GenAI pro underwriting
Název banky:     Horizon Bank
Logo:            static/horizon_logo.png (base64 v sidebar)
Font:            Manrope (Google Fonts)
Primární barva:  #4D25EB (ACCENT)
Hover barva:     #3A1BB8 (ACCENT_DARK)
Text hlavní:     #0B0F17 (TEXT_MAIN)
Text sekundární: #4B5563 (TEXT_SEC)
Oddělovač:       #E5E7EB (DIVIDER)
Povrch / karty:  #F9FAFB (SURFACE)
Pozadí:          #FFFFFF (BG)
```

---

## UI Navigace (app.py)

```python
pages = {
    "portfolio":   "📊 Portfolio + EWS",
    "credit_memo": "📄 Credit Memo",
    "human_review":"👁️ Human Review",
    "cases_log":   "📋 Cases Log",
    "settings":    "⚙️ Nastavení",
}
```

**Portfolio stránka layout:**
1. KPI karty (klientů, GREEN/AMBER/RED)
2. EWS sekce (nahoře! — ▶ Spustit EWS analýzu)
3. Filtr Early Warning (radio)
4. List klientů (bez "Generovat memo" tlačítka)
5. Skills Library expander

---

## Databricks — batch queries pattern

```python
# get_portfolio_clients() — 3 batch queries místo N+1

# Batch 1: Silver 3-way JOIN
FROM silver_corporate_financial_profile fp
JOIN silver_corporate_customer cc ON cc.customer_id = fp.customer_id
JOIN silver_company_master cm ON CAST(cm.ico AS STRING) = CAST(cc.ico AS STRING)
WHERE fp.is_current = TRUE

# Batch 2: CRIBIS batch (normalizované IČO!)
FROM vse_banka.investment_banking.silver_data_cribis_v3
WHERE CAST(TRY_CAST(ic AS BIGINT) AS STRING) IN ('{ico_list_norm}')
QUALIFY ROW_NUMBER() OVER (PARTITION BY ic ORDER BY obdobi_do DESC) = 1

# Batch 3: covenant_status
FROM silver_credit_history WHERE ico IN ('{ico_list}')
```

---

## LLM Factory

```python
from utils.llm_factory import get_llm

llm = get_llm()   # čte LLM_PROVIDER + LLM_MODEL z env
resp = llm.complete(
    system=skill["prompt"],
    user_message=context_json,
    max_tokens=2048,
)
text   = resp.text
tokens = resp.tokens_used
```

Výchozí modely:
- `anthropic` → `claude-opus-4-6`
- `openai` → `gpt-4o`

---

## Skills Management

```python
from skills import registry

# Načtení
skill = registry.get("maker_skill")
prompt = skill["prompt"]
version = skill["version"]
ph = registry.get_prompt_hash("maker_skill")  # sha256[:12]

# Uložení nového skill (UI formulář volá toto)
path = registry.save_skill("my_team_skill", {
    "name": "My Team Agent",
    "version": "1.0",
    "author": "my_team",
    "node_type": "AI",   # nebo "DETERMINISTIC"
    "language": "cs",
    "approved_by": "risk_mgmt",
    "approved_at": "2026-04-15",
    "constraints": ["NIKDY nepočítej matematiku"],
    "data_sources_required": ["company_master"],
    "prompt": "Jsi agent pro...",
})
# → zapíše skills/my_team_skill.yaml, invaliduje cache

# Smazání
registry.delete_skill("my_team_skill")
```

---

## WCR Limity

```python
WCR_LIMITS = {
    "max_leverage_ratio":  5.0,   # Net Debt / EBITDA ≤ 5.0x
    "min_dscr":            1.2,   # DSCR ≥ 1.2
    "max_utilisation_pct": 85.0,  # Využití limitu ≤ 85%
    "min_current_ratio":   1.2,   # Current Ratio ≥ 1.2
    "max_dpd_days":        30,    # DPD ≤ 30 dní
}

WCR_WARNINGS = {         # soft limity — sledovat, ne breach
    "icr_warning_threshold": 3.0,
    "max_debt_to_equity":    3.0,
    "min_equity_ratio":      0.20,
    "min_quick_ratio":       1.0,
}

EW_THRESHOLDS = {
    "utilisation_red_pct":    85.0,
    "utilisation_amber_pct":  75.0,
    "dpd_red_days":           30.0,
    "dpd_amber_days":         15.0,
    "revenue_drop_red_pct":   20.0,
    "revenue_drop_amber_pct": 10.0,
    "overdraft_red_pct":      50.0,
    "overdraft_amber_pct":    20.0,
    "tax_compliance_amber":   67.0,
    "covenant_risk_red":       0.7,
    "covenant_risk_amber":     0.5,
}

MIN_CITATION_COVERAGE  = 0.90
MAX_MAKER_ITERATIONS   = 3
API_RETRY_COUNT        = 3
API_RETRY_DELAY_SEC    = 30
```

---

## Mock Portfolio (6 klientů)

| IČO | Název | EW Level | WCR |
|-----|-------|----------|-----|
| 27082440 | Stavební holding Praha a.s. | GREEN | PASS |
| 45274649 | Logistika Morava s.r.o. | RED | FAIL (DSCR + util) |
| 00514152 | Energetika Brno a.s. | GREEN | PASS |
| 26467054 | Retail Group CZ s.r.o. | AMBER | FAIL (util) |
| 63999714 | Farmaceutika Nord a.s. | GREEN | PASS |
| 49551895 | Textil Liberec s.r.o. | RED | FAIL (4 breaches) |

---

## Spuštění

```bash
# Demo
ICM_ENV=demo streamlit run app.py

# Production
ICM_ENV=production streamlit run app.py

# Smoke testy
python -m utils.calculator
python -m utils.wcr_rules
python -m utils.mock_data
python -m utils.data_connector
python -m utils.audit
python -m utils.llm_factory
python -m pipeline.nodes.phase2_analysis
python -m pipeline.nodes.phase3_maker_checker
python -m pipeline.nodes.phase4_human_audit
python -m early_warning.graph
python -m esg_pipeline.dispatcher

# Celá DP1 pipeline
ICM_ENV=demo python -m pipeline.graph 27082440
```

---

## Gаpy oproti Data Lineage diagramu (v3)

Diagram ukazuje ideální architekturu. Níže jsou delta oproti skutečné implementaci:

### ❌ Není implementováno (blocker pro prod)

**Bronze Layer / ICM Data Lake (Retention 90 dní)**
- Kód jde přímo Silver → pipeline. Žádná raw vrstva, žádné 90denní archivace.
- Při implementaci: přidat Bronze schema, retention policy, raw ingest writer.

**Quarantine Zone**
- Diagram: při DQ chybě → karanténa → auto-oprava → Data Steward review → Reject+Log.
- Skutečnost: `ProcessStatus.FROZEN` — pipeline se zastaví, ale data jdou do karantény pouze v paměti.
- Chybí: karanténní tabulka, auto-oprava ICO, notifikace adminům, Data Steward workflow.

**Helios / SharePoint integrace (downstream)**
- Diagram: draft → reviewed → approved · versioned v Helios/SharePoint.
- Skutečnost: Credit Memo je pouze v Streamlit UI. Žádný export.

**CMP / CBS / CRM upstream**
- Risk systémy (CMP), Tým 3 CBS Core Banking, Tým 3 CRM nejsou v `data_connector.py`.

### ⚠️ Částečně implementováno (TODO v kódu)

**ESG Datamart prod write** (`esg_pipeline/dispatcher.py`)
```python
# TODO: INSERT INTO vse_banka.icm_gen_ai.esg_cross_domain_datamart
# (zakomentováno v dispatcher.py)
```

**EWS Delta write + notifikace** (`early_warning/nodes/alert_dispatcher.py`)
```python
# TODO: INSERT INTO ews_alerts
# TODO: Notifikace Risk Mgmt přes Databricks Workflow
```

**PII Masking**
- Diagram: PII Masking na Silver vrstvě při ingesci.
- Skutečnost: GDPR sanitize je až po human approval v `phase4_human_audit.py`.

**Anti-Hallucination Guard (Bronze)**
- Diagram: Anti-Hallucination Guard je już v Bronze vrstvě.
- Skutečnost: hallucination check je až v `QualityControlChecker` (phase 3 pipeline).

### ✅ Plně implementováno (shoduje se s diagramem)

- Single source of truth = Databricks Silver
- Case View (CaseView objekt, phase2)
- Memo Preparation Agent + LLM Draft (phase3)
- 4-Eyes Rule = HumanReviewNode (phase4)
- Immutable Audit Trail s prompt hashy
- Cascade fallback: CRIBIS → Justice.cz → ARES → Freeze
- ICO resolution (`_norm_ico()`)
- Lineage preserved (source_id v každém audit eventu)
- ESG pipeline architektura (collector → transformer → dispatcher)
- EWS portfolio monitoring (celý DP2 graf)

---

## Audit log změn

| Datum | Co | Výsledek |
|-------|----|---------|
| 2026-04-14 | Initial audit (Senior IT Auditor) | 4 PASS, 3 WARNING → opraveno; 0 FAIL |
| 2026-04-15 | Rebranding → Horizon Bank, logo | sidebar, page headers, mock memos |
| 2026-04-15 | EWS přesun nad list klientů | portfolio page layout |
| 2026-04-15 | Odstranění "Generovat memo" z řádků | page_portfolio.py |
| 2026-04-15 | CRIBIS JOIN fix — vedoucí nuly | `_norm_ico()` + `TRY_CAST(ic AS BIGINT)` |
| 2026-04-15 | WCR skipped fix — None ≠ breach | phase3_maker_checker + page_credit_memo |
| 2026-04-15 | WCR description field přidán | policy_rules_engine rules_detail |
| 2026-04-15 | "Nonex" bug fix | val_str guard v _render_wcr_tab |
| 2026-04-15 | Skills Management UI — tab ➕ | page_settings.py + registry.save_skill |
| 2026-04-15 | CRIBIS live diagnostika | Databricks tab — ▶ Spustit CRIBIS test |
| 2026-04-15 | Financial metrics tab přepsán | Silver + CRIBIS raw data separátně |
