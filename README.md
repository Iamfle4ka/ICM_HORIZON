# ICM GenAI Platform
**Tým 7 · Institutional Credit Management · Citi · Horizon AI bank**

AI-powered systém pro automatizované generování Credit Memo
a Early Warning monitoring kreditního portfolia.

---

## Architektura

```
Upstream → Bronze → [Quarantine] → Silver ──────────────────────┐
                                      │                          │
                              Databricks Medallion         ESG Pipeline
                              (vse_banka.obsluha_klienta)  → Cross-Domain
                                      │                     Datamart Tým 5
                              CRIBIS (Tým 8)
                              (investment_banking)
                                      │
                    ┌─────────────────┴──────────────────┐
                    │                                    │
             DP1: Credit Memo                   DP2: Early Warning
             ─────────────────                   ──────────────────
             DataExtractor (AI)                  PortfolioLoader
                ↓                                     ↓
             [Fallback: Justice.cz PDF]          MetricsCalculator
                ↓                                     ↓
             ContextBuilder (DET)               AnomalyDetector
                ↓                               (rules + AI text)
             CreditAnalysisService                    ↓
             (calculator.py — DET)               AlertGenerator
                ↓                                     ↓
             MakerAgent (AI)                    AlertDispatcher
                ↓
             CheckerAgent (AI)
                ↓
             PolicyRulesEngine (DET)
                ↓
             Human-in-the-Loop (4-Eyes)
                ↓
             GDPR Sanitize → AuditEngine
```

---

## Spuštění

```bash
# Instalace
pip install -r requirements.txt

# Demo (bez Databricks a bez API klíče)
ICM_ENV=demo streamlit run app.py

# S API klíčem (AI uzly aktivní)
cp .env.example .env   # vyplň ANTHROPIC_API_KEY
export $(cat .env | xargs)
streamlit run app.py

# Production (Databricks)
# Odkomentuj databricks-sql-connector v requirements.txt
# Nastav ICM_ENV=production a Databricks credentials v .env
```

---

## Stránky UI

| Stránka | Popis |
|---------|-------|
| 📊 Portfolio | Portfolio State Store, EW alerty, filtry |
| 📄 Credit Memo | DP1 pipeline, WCR tabulka, výsledek |
| ⚠️ Early Warning | DP2 pipeline, RED/AMBER/GREEN alerty |
| 👁️ Human Review | 4-Eyes schválení / zamítnutí / revize |
| 🔍 Audit Trail | Prompt hashe, tokeny, full trace |
| ⚙️ Nastavení | WCR limity, Skills Library, Databricks status |

---

## Klíčové principy

| Princip | Implementace |
|---------|-------------|
| LLM nepočítá matematiku | `utils/calculator.py` — deterministické vzorce |
| Checker ≠ WCR validator | Checker dělá Evidence Mapping; WCR = PolicyRulesEngine |
| DSCR je proxy | `(EBITDA−CAPEX−Taxes) / (Interest + Principal)` |
| CAPEX z 2 období | `ΔFA + odpisy`; proxy = pouze odpisy pokud chybí prev. |
| Žádný T-1 fallback | API failure → `ProcessStatus.FROZEN` |
| ESG není v Credit Memo | Oddělená pipeline pro Tým 5 |
| Kaskádový fallback | CRIBIS → Justice.cz PDF → ARES → Process Freeze |
| Transient Sessions | GDPR cleanup v `phase4_human_audit._sanitize_transient_data()` |
| Prompt hash | `_audit(prompt=skill["prompt"])` → sha256[:12] v každém AI uzlu |

---

## WCR Limity (Risk Management approved)

| Koeficient | Limit | Zdroj dat |
|-----------|-------|-----------|
| Leverage (Net Debt/EBITDA) | ≤ 5.0x | CRIBIS |
| DSCR (proxy) | ≥ 1.2 | CRIBIS |
| Current Ratio | ≥ 1.2 | CRIBIS |
| DPD | ≤ 30 dní | silver_credit_history |
| Utilisation | ≤ 85% | silver_credit_history |

**WCR Varování (soft limity):**

| Koeficient | Práh | Akce |
|-----------|------|------|
| ICR (EBITDA/Interest) | < 3.0x | Varování, sledovat |
| D/E Ratio | > 3.0x | Varování |
| Equity Ratio | < 20% | Varování |
| Quick Ratio | < 1.0 | Varování |

---

## Databricks Tabulky

| Tabulka | Catalog.Schema | Účel |
|---------|---------------|------|
| silver_company_master | vse_banka.obsluha_klienta | Identifikace firmy |
| silver_corporate_financial_profile | ... | Finanční profil (SCD Type 2) |
| silver_credit_history | ... | Kovenanty, DPD, utilisation |
| silver_transactions | ... | 12M transakce |
| silver_client_incidents | ... | CRM incidenty |
| silver_data_cribis_v3 | vse_banka.investment_banking | EBITDA, ratia, trendy (CRIBIS) |
| silver_ruian_buildings | vse_banka.icm_gen_ai | Budovy + GPS |
| silver_building_flood_join | ... | Flood risk zóny Q5/Q20/Q100 |

---

## Mock Portfolio (demo mode)

| IČO | Název | EW Level | WCR |
|-----|-------|----------|-----|
| 27082440 | Stavební holding Praha a.s. | GREEN | PASS |
| 45274649 | Logistika Morava s.r.o. | RED | FAIL (DSCR + util) |
| 00514152 | Energetika Brno a.s. | GREEN | PASS |
| 26467054 | Retail Group CZ s.r.o. | AMBER | FAIL (util) |
| 63999714 | Farmaceutika Nord a.s. | GREEN | PASS |
| 49551895 | Textil Liberec s.r.o. | RED | FAIL (4 breaches) |

---

## Struktura projektu

```
icm-genai-platform/
├── app.py                     Streamlit vstupní bod
├── pipeline/                  DP1: Credit Memo pipeline
│   ├── state.py               AgentState TypedDict + ProcessStatus
│   ├── graph.py               LangGraph StateGraph (build_graph, run_pipeline)
│   ├── routing.py             Podmíněné hrany (DETERMINISTIC)
│   └── nodes/
│       ├── phase1_extraction.py   DataExtractorAgent + ExtractionValidator
│       ├── phase2_analysis.py     ContextBuilder + CreditAnalysisService
│       ├── phase3_maker_checker.py MemoPreparationAgent + QualityControlChecker
│       └── phase4_human_audit.py  HumanReviewNode + RecordHumanDecision + GDPR
├── early_warning/             DP2: EWS pipeline
│   ├── graph.py               EWS LangGraph
│   └── nodes/                 portfolio_loader → metrics_calculator → anomaly_detector
├── esg_pipeline/              ESG pipeline (pro Tým 5, ne Credit Memo)
├── skills/                    YAML prompt definice (verzované, hashované)
│   ├── extractor_skill.yaml   DataExtractor v2.3
│   ├── maker_skill.yaml       MemoPreparation v3.1
│   ├── checker_skill.yaml     QualityControl v2.0
│   ├── esg_skill.yaml         ESGAnalysis v1.5
│   ├── ew_analyzer_skill.yaml EWS AI doporučení
│   └── calculator_skill.yaml  Formula library (DETERMINISTIC, jen dokumentace)
├── utils/
│   ├── calculator.py          Deterministický výpočetní engine (CAPEX, DSCR, atd.)
│   ├── data_connector.py      Databricks connector (IS_DEMO přepínač)
│   ├── data_fetcher.py        Kaskádový fallback (CRIBIS→Justice→ARES→Freeze)
│   ├── news_fetcher.py        EWS signály (ISIR + ČNB + Google News)
│   ├── wcr_rules.py           WCR limity + EW prahy + WCR_WARNINGS
│   ├── audit.py               _audit() — immutable append-only audit trail
│   ├── mock_data.py           6 mock klientů pro demo
│   └── chunking.py            semantic_chunk() pro dokumenty
└── ui/                        Streamlit stránky (6 stránek)
```

---

*ICM GenAI Platform · Tým 7 · Citi Bank Hackathon · Horizon AI bank*
