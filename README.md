# ICM GenAI Platform

**AI-asistovaný systém kreditní analýzy** · Citi Bank · Tým 7

---

## O projektu

ICM GenAI Platform automatizuje tvorbu Credit Mem pro korporátní klienty.
Pipeline kombinuje deterministické finanční výpočty s AI (Claude) pro psaní mema,
při zachování plného auditovatelnosti a 4-Eyes Rule.

## Architektura pipeline

```
Phase 1 — Extrakce dat
  DataExtractorAgent (AI)     ← Claude extrahuje data z dokumentů
  ExtractionValidator (DET)   ← kontrola confidence_score ≥ 0.85

Phase 2 — Analýza (DETERMINISTIC)
  ContextBuilder              ← sestaví CaseView z extrakce
  CreditAnalysisService       ← vypočítá leverage, DSCR, current ratio

Phase 3 — Maker-Checker Loop (max 3 iterace)
  MemoPreparationAgent (AI)   ← Claude píše Credit Memo
  QualityControlChecker (AI)  ← Claude kontroluje citace a halucinace
  PolicyRulesEngine (DET)     ← WCR limity (čistý Python)

Phase 4 — Human Review
  HumanReviewNode (DET)       ← status AWAITING_HUMAN
  RecordHumanDecision (DET)   ← underwriter: schválit / zamítnout
```

## Klíčové vlastnosti

- **4-Eyes Rule**: každé memo musí schválit underwriter
- **Deterministická matematika**: LLM nikdy nepočítá finanční metriky
- **Immutable Audit Trail**: každá akce loggována s prompt hashem
- **Process Freeze**: při API selhání → zmražení (NE T-1 fallback)
- **Citation Coverage**: ≥ 90 % čísel musí mít `[CITATION:source_id]`
- **Maker-Checker Loop**: max 3 iterace s automatickou eskalací

## Rychlý start

```bash
pip install streamlit langgraph anthropic pyyaml
streamlit run app.py
```

Aplikace se otevře na `http://localhost:8501`.

## Stránky UI

| Stránka | Popis |
|---------|-------|
| Portfolio Dashboard | Přehled 6 klientů, EW status, WCR metriky |
| Credit Memo | Spuštění AI pipeline, generování mema |
| Human Review | 4-Eyes Rule — schválit / zamítnout |
| Audit Trail | Immutable log, AI vs. DET rozlišení |

## Mock portfolio

6 klientů s různými rizikovými profily (GREEN/AMBER/RED) pro demo a testování.
IČO pro testování: `27082440`, `45274649`, `00514152`, `26467054`, `63999714`, `49551895`

## Technologie

- **LangGraph** — orchestrace pipeline jako StateGraph
- **Claude (Anthropic)** — AI uzly (extrakce, maker, checker)
- **Streamlit** — webové UI
- **Python** — deterministické výpočty, WCR pravidla, audit trail
- **YAML Skills** — verzované a hashované prompty

---

*ICM GenAI Platform · Tým 7 · Citi Bank Hackathon*
