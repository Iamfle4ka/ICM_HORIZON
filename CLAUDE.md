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
    phase2_analysis.py         ← DET: ContextBuilder + CreditAnalysisService
    phase3_maker_checker.py    ← AI: MemoPreparationAgent, QualityControlChecker + DET: PolicyRulesEngine
    phase4_human_audit.py      ← DET: HumanReviewNode + RecordHumanDecision
skills/
  __init__.py                  ← SkillsRegistry (YAML loader, cache, hash)
  extractor_skill.yaml         ← DataExtractor prompt v2.3
  maker_skill.yaml             ← MemoPreparation prompt v3.1
  checker_skill.yaml           ← QualityControl prompt v2.0
  esg_skill.yaml               ← ESGAnalysis prompt v1.5
utils/
  wcr_rules.py                 ← WCR limity + check_wcr_breaches + build_wcr_report
  audit.py                     ← _audit() — immutable append-only audit trail
  mock_data.py                 ← 6 mock klientů s předem vypočtenými metrikami
  chunking.py                  ← semantic_chunk() — dělení dokumentů
ui/
  styles.py                    ← CSS, barvy, helper funkce
  page_portfolio.py            ← Portfolio Dashboard
  page_credit_memo.py          ← Credit Memo Generator
  page_human_review.py         ← 4-Eyes Rule Human Review
  page_audit_trail.py          ← Immutable Audit Trail Viewer
```

---

## Klíčová pravidla (NIKDY neporušovat)

### 1. Deterministika vs. AI

- Komentář `# DETERMINISTIC` — čistý Python, žádný LLM
- Komentář `# AI` — volá Claude API přes `anthropic.Anthropic()`
- **LLM NIKDY nepočítá matematiku** — leverage_ratio, DSCR, current_ratio, utilisation_pct jsou vždy vypočteny deterministicky v `credit_analysis_service`

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
- Po schválení: citlivá data jsou vyčištěna (práce probíhá)

---

## Spuštění

```bash
# Instalace závislostí
pip install streamlit langgraph anthropic pyyaml

# Spuštění aplikace
streamlit run app.py

# Smoke testy (jednotlivé moduly)
python utils/wcr_rules.py
python utils/audit.py
python pipeline/state.py
python utils/mock_data.py
python pipeline/nodes/phase2_analysis.py
python pipeline/nodes/phase1_extraction.py
python pipeline/nodes/phase3_maker_checker.py
python pipeline/nodes/phase4_human_audit.py
python pipeline/routing.py

# Spuštění celé pipeline (demo mode)
python pipeline/graph.py 27082440
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
| DSCR (Op. CF / Debt Service) | ≥ 1.2 |
| Využití limitu | ≤ 85 % |
| Current Ratio | ≥ 1.0 |
| DPD | ≤ 30 dní |

---

## Závislosti

```
streamlit>=1.35
langgraph>=0.2
anthropic>=0.25
pyyaml>=6.0
```
