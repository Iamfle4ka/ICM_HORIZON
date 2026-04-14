# ICM GenAI Platform — CLAUDE.md
## Developer Context for Claude Code

---

## Projekt

ICM GenAI Platform je AI-asistovaný systém pro kreditní analýzu v Citi Bank.
Tým 7 · Hackathon projekt · LangGraph + Claude API + Streamlit.

---

## Architektura

```
app.py                         ← Streamlit entry point
pipeline/
  state.py                     ← AgentState, ProcessStatus (TypedDict)
  graph.py                     ← LangGraph StateGraph (build_graph, run_pipeline)
  routing.py                   ← Podmíněné hrany (DETERMINISTIC)
  nodes/
    phase1_extraction.py       ← AI: DataExtractorAgent + DET: ExtractionValidator
    phase2_analysis.py         ← DET: ContextBuilder + CreditAnalysisService (→ calculator.py)
    phase3_maker_checker.py    ← AI: MemoPreparationAgent, QualityControlChecker + DET: PolicyRulesEngine
    phase4_human_audit.py      ← DET: HumanReviewNode + RecordHumanDecision + GDPR sanitize
skills/
  __init__.py                  ← SkillsRegistry (YAML loader, cache, hash)
  extractor_skill.yaml         ← DataExtractor prompt v2.3
  maker_skill.yaml             ← MemoPreparation prompt v3.1
  checker_skill.yaml           ← QualityControl prompt v2.0
  esg_skill.yaml               ← ESGAnalysis prompt v1.5
  ew_analyzer_skill.yaml       ← EWS AI doporučení (recommended_action text)
  calculator_skill.yaml        ← Formula library dokumentace (node_type: DETERMINISTIC)
early_warning/
  graph.py                     ← EWS LangGraph pipeline (DP2)
  nodes/
    portfolio_loader.py        ← DET: načte ACTIVE klienty + CRIBIS enrichment
    metrics_calculator.py      ← DET: utilisation, DPD, overdraft, tax compliance
    anomaly_detector.py        ← DET: pravidla + AI text recommended_action + News signály
    alert_generator.py         ← DET: sestaví alerts pro UI
    alert_dispatcher.py        ← DET: dispatch do Risk Management
esg_pipeline/                  ← ESG pro Tým 5 POUZE (nesouvisí s Credit Memo)
  collector.py                 ← flood risk, ESG score raw
  transformer.py               ← AI: ESGTransformerAgent
  dispatcher.py                ← DET: INSERT do esg_cross_domain_datamart
utils/
  wcr_rules.py                 ← WCR_LIMITS + WCR_WARNINGS + EW_THRESHOLDS + check_wcr_breaches
  calculator.py                ← compute_all_metrics() — DSCR+CAPEX, leverage, ratia (DET)
  data_connector.py            ← Databricks Silver + CRIBIS + flood risk (IS_DEMO přepínač)
  data_fetcher.py              ← Kaskádový fallback (CRIBIS→Justice.cz→ARES→Freeze)
  news_fetcher.py              ← EWS signály (ISIR, ČNB sazba, Google News)
  audit.py                     ← _audit() — immutable append-only audit trail
  mock_data.py                 ← 6 mock klientů + _mock_cribis() + _mock_cribis_prev()
  chunking.py                  ← semantic_chunk() — dělení dokumentů
ui/
  styles.py                    ← CSS, barvy, helper funkce
  page_portfolio.py            ← Portfolio Dashboard
  page_credit_memo.py          ← Credit Memo Generator
  page_human_review.py         ← 4-Eyes Rule Human Review
  page_audit_trail.py          ← Immutable Audit Trail Viewer
  page_early_warning.py        ← EWS Dashboard (DP2)
  page_settings.py             ← WCR limity, Skills Library, Databricks status
```

---

## Klíčová pravidla (NIKDY neporušovat)

### 1. Deterministika vs. AI

- Komentář `# DETERMINISTIC` — čistý Python, žádný LLM
- Komentář `# AI` — volá Claude API přes `anthropic.Anthropic()`
- **LLM NIKDY nepočítá matematiku** — veškeré metriky přes `utils/calculator.py`
- `compute_all_metrics(cribis, internal, cribis_prev)` je jediný vstupní bod

### 2. Audit Trail

- `_audit()` z `utils/audit.py` musí být voláno v každém uzlu
- Audit trail je **append-only** — nikdy nepřepisuj existující eventy
- AI uzly: `prompt=skill["prompt"]` → automaticky se hashuje sha256[:12]
- DET uzly: `prompt=None` → `prompt_hash=None` v logu

### 3. API Failure → Process Freeze

- Při selhání Claude API: `status = ProcessStatus.FROZEN`
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
  `extraction_result`, `case_view`, `draft_memo`, `financial_metrics` (raw hodnoty)
- Audit trail zůstává — neobsahuje raw finanční data, pouze hashe a metadata

### 7. Data Sources & Fallback

- Primární: CRIBIS (`vse_banka.investment_banking.silver_data_cribis_v3`)
- CRIBIS klíč: `ic` (ne `ico`) → CAST nutný: `WHERE CAST(ic AS STRING) = '{ico}'`
- Fallback kaskáda: CRIBIS → Justice.cz PDF → ARES API → Process Freeze
- Viz `utils/data_fetcher.py` — `fetch_financial_data(ico)` → `FetchResult`
- CRIBIS prev period: `get_cribis_prev_period(ico)` — pro CAPEX výpočet (`OFFSET 1`)
- ESG: `utils/data_connector.get_flood_risk(city)` — pouze pro ESG pipeline (Tým 5)

### 8. DSCR vzorec (CAPEX-adjusted)

```
DSCR = (EBITDA - CAPEX - Taxes) / (Interest + bank_liabilities_st / 12)
CAPEX = max(0, fixed_assets_curr - fixed_assets_prev) + odpisy
       → pokud prev chybí: CAPEX_proxy = odpisy (konzervativnější)
```

---

## Spuštění

```bash
# Instalace závislostí
pip install -r requirements.txt

# Spuštění aplikace (demo mode)
ICM_ENV=demo streamlit run app.py

# Smoke testy
python -m utils.calculator
python -m utils.wcr_rules
python -m utils.mock_data
python -m utils.data_connector
python -m utils.data_fetcher
python -m utils.news_fetcher
python -m pipeline.nodes.phase2_analysis
python -m pipeline.nodes.phase4_human_audit
python -m early_warning.graph
python -m esg_pipeline.dispatcher

# Celá DP1 pipeline (demo mode)
ICM_ENV=demo python -m pipeline.graph 27082440
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

## WCR Limity (Risk Management approved)

| Pravidlo | Limit |
|----------|-------|
| Leverage Ratio (Net Debt/EBITDA) | ≤ 5.0x |
| DSCR (CAPEX-adjusted proxy) | ≥ 1.2 |
| Využití limitu | ≤ 85 % |
| Current Ratio | ≥ 1.2 |
| DPD | ≤ 30 dní |

**WCR_WARNINGS (soft limity — ne breach):**

| Koeficient | Práh |
|-----------|------|
| ICR (EBITDA/Interest) | < 3.0x |
| D/E Ratio | > 3.0x |
| Equity Ratio | < 20% |
| Quick Ratio | < 1.0 |

---

## Závislosti

```
pip install -r requirements.txt
# langgraph>=0.2.0, anthropic>=0.40.0, streamlit>=1.35.0
# pyyaml>=6.0, python-dotenv>=1.0.0
```

---

## Audit log

| Datum | Co | Výsledek |
|-------|----|---------|
| 2026-04-14 | Initial audit (Senior IT Auditor) | 4 PASS, 3 WARNING → opraveno; 0 FAIL |
