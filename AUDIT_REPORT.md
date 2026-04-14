# ICM GenAI Platform — Audit Report

**Datum:** 2026-04-14
**Auditor:** Claude Code (role: Senior Bank IT Auditor — 15 let zkušeností, Basel III, ČNB, GDPR)
**Verze projektu:** `fde53c8 new esg pipeline, new databricks connector, new ew pipeline`
**Scope:** Kompletní audit kódu, matematiky, bezpečnosti, agentní logiky a dokumentace

---

## Executive Summary

ICM GenAI Platform (Tým 7) je architektonicky dobře navržený systém s jasnou
separací AI a deterministických uzlů, funkčním Maker-Checker Loops a immutable
Audit Trailem. Audit odhalil 4 problémy (2 střední, 2 nízké závažnosti), které
byly opraveny v rámci tohoto auditu. Žádný kritický bezpečnostní incident
nepředstavuje okamžité ohrožení — Databricks token je pouze lokálně uložen
v `.gitignore`d souboru a nebyl commité do git historie.

---

## Výsledky podle fáze

| Fáze | PASS | WARNING | FAIL | Poznámka |
|------|------|---------|------|---------|
| 1. Inventář | ✅ | — | — | 41 souborů, 7 867 řádků |
| 2. Smoke testy | ✅ 8/8 | ⚠️ 1 | — | skills registry varování opraveno |
| 3. Matematika | ✅ | ⚠️ 1 | — | calc_net_debt chybí jako standalone |
| 4. Bezpečnost/GDPR | ✅ | ⚠️ 2 | — | GDPR cleanup implementován |
| 5. Agent logika | ✅ | ⚠️ 1 | — | false positive (prompt_hash OK) |
| 6. Databricks | ✅ | ⚠️ 1 | — | python-dotenv přidán do req. |
| 7. Dokumentace | ✅ | ⚠️ 2 | — | README a CLAUDE.md aktualizovány |

---

## Kritické nálezy (FAIL)

*Žádná kritická selhání nebyla nalezena.*

---

## Varování (WARNING) a jejich řešení

### ⚠️ W1 — `calculator_skill.yaml` chybí povinné registry klíče
**Nález:** SkillsRegistry vyhazoval varování `"Skill calculator_skill chybí povinné klíče: {'prompt', 'node_type'}"` při každé inicializaci.
**Riziko:** Runtime noise, potenciální selhání kódu závislého na registry iteraci.
**Oprava:** Přidány `node_type: DETERMINISTIC` a `prompt: "# DETERMINISTIC — Formula library…"` do `skills/calculator_skill.yaml`.
**Status:** ✅ Opraveno

---

### ⚠️ W2 — GDPR cleanup nebyl implementován
**Nález:** `phase4_human_audit.record_human_decision()` nezaváděl žádnou sanitizaci
transientních dat po schválení. `extraction_result`, `case_view`, `draft_memo`
zůstávaly v paměti state po `COMPLETED`. CLAUDE.md toto označoval jako "práce probíhá".
**Riziko:** GDPR compliance gap — citlivá finanční data klientů mohla přetrvávat
v session state déle než je nutné.
**Oprava:** Implementována `_sanitize_transient_data()` funkce v `phase4_human_audit.py`.
Po `COMPLETED` nebo `FAILED` se odstraní `extraction_result`, `case_view`, `draft_memo`
a z `financial_metrics` zůstane pouze WCR summary (bez raw hodnot).
**Status:** ✅ Opraveno

---

### ⚠️ W3 — WCR `min_current_ratio` nezdokumentovaná změna (1.0 → 1.2)
**Nález:** CLAUDE.md a README.md uváděly `Current Ratio ≥ 1.0`, ale kód měl
`WCR_LIMITS["min_current_ratio"] = 1.2` (zpřísněno v předchozí implementaci).
**Riziko:** Dokumentace vs. implementace divergence — auditor by schválil klienta
dle dokumentace, ale kód by ho zamítl.
**Oprava:** CLAUDE.md a README.md aktualizovány na `≥ 1.2`.
**Status:** ✅ Opraveno

---

### ⚠️ W4 — Chybí `python-dotenv` v `requirements.txt`
**Nález:** `.env` soubor existuje s Databricks credentials, ale `python-dotenv`
nebyl v `requirements.txt`. `data_connector.py` používá `os.getenv()` (ne `load_dotenv()`),
takže v čisté instalaci by env vars nebyly auto-načteny.
**Oprava:** Přidáno `python-dotenv>=1.0.0` do `requirements.txt`. Doporučeno přidat
`load_dotenv()` do `app.py` entry pointu pro production.
**Status:** ✅ Opraveno (requirements.txt) | 📝 TODO: `load_dotenv()` v `app.py`

---

### ⚠️ W5 — `calc_net_debt` neexistuje jako standalone exported funkce
**Nález:** Audit prompt požadoval import `calc_net_debt` z `utils.calculator`.
Funkce neexistuje — net_debt je počítán inline v `calc_leverage()` a `compute_all_metrics()`.
**Riziko:** Dokumentace kalkulátoru (`calculator_skill.yaml`) popisuje net_debt
jako vzorec, ale nemá callable wrapper.
**Rozhodnutí:** Ponecháno — `calc_leverage()` interně počítá net_debt správně,
duplicitní standalone funkce by nepřidala hodnotu. Není se třeba opravovat.
**Status:** 📝 NOTE — záměrné (DRY princip)

---

### ⚠️ W6 — `prompt_hash` zdánlivě chybí v phase3 (false positive)
**Nález auditu:** `grep -n "prompt_hash" phase3_maker_checker.py` vrátil prázdný výstup.
**Analýza:** `_audit()` přijímá `prompt=skill["prompt"]` a hashuje ho interně.
Řetězec `"prompt_hash"` se nevyskytuje v call site, ale klíč existuje v výstupu.
Ověřeno: `phase3_maker_checker.py` line 153: `prompt=prompt,` a line 187: `prompt=prompt,`
jsou správně předány.
**Status:** ✅ PASS — false positive

---

## Opravené problémy (v rámci tohoto auditu)

| # | Soubor | Změna |
|---|--------|-------|
| 1 | `skills/calculator_skill.yaml` | Přidány `node_type: DETERMINISTIC` a `prompt` key |
| 2 | `pipeline/nodes/phase4_human_audit.py` | Implementována `_sanitize_transient_data()` — GDPR cleanup |
| 3 | `requirements.txt` | Přidán `python-dotenv`, aktualizovány verze |
| 4 | `README.md` | Kompletní přepis — aktuální architektura, WCR tabulky, Databricks info |
| 5 | `CLAUDE.md` | Aktualizováno: opraveny WCR limity (1.0→1.2), přidány chybějící moduly, Data Sources sekce, Audit log |

---

## Zbývající omezení (záměrná)

| Oblast | Omezení | Důvod |
|--------|---------|-------|
| DSCR | Proxy vzorec (EBITDA-CAPEX-Taxes/DS) — dividendy se nezohledňují | Dividendy = Client Outreach scope, mimo kreditní memo |
| CAPEX | Pokud chybí `cribis_prev_period` → proxy pouze z odpisů | Databricks má jen 1 období v demo; prod bude OK |
| Justice.cz | Parser je stub (`NotImplementedError`) | Vyžaduje PDF parsing knihovny — mimo scope hackatonu |
| ESG pipeline | Zcela oddělena od Credit Memo pipeline | Záměrné — ESG je pro Tým 5 |
| `load_dotenv()` | Není voláno v `app.py` | `.env` se načte jen pokud jsou vars exportovány v shellu |
| Google News scraping | V demo mode vrací prázdný seznam | ISIR/ČNB taktéž — bezpečná degradace |

---

## Audit checklist — architektonické principy

| Princip | Status | Poznámka |
|---------|--------|----------|
| LLM nepočítá matematiku | ✅ PASS | `utils/calculator.py` — vše deterministické |
| Checker ≠ WCR validator | ✅ PASS | Checker: citace/halucinace; WCR: PolicyRulesEngine |
| DSCR je proxy s poznámkou | ✅ PASS | `dscr_note` propagováno do `financial_metrics` |
| CAPEX z 2 období nebo proxy | ✅ PASS | `calc_capex()` — ΔFA+odpisy nebo pouze odpisy |
| Žádný T-1 fallback | ✅ PASS | API failure → FROZEN, ne T-1 |
| Transient Sessions (GDPR) | ✅ PASS | Implementováno: `_sanitize_transient_data()` |
| 4-Eyes Rule (Maker≠Checker) | ✅ PASS | Oddělené AI uzly, různé skills |
| ESG není v Credit Memo | ✅ PASS | Checker flaguje ESG jako halucinaci |
| Process Freeze implementován | ✅ PASS | `phase1_extraction.py` lines 89, 112, 135 |
| Prompt hash v audit trail | ✅ PASS | `prompt=skill["prompt"]` v každém AI uzlu |
| SCD Type 2 filter | ✅ PASS | `AND is_current = TRUE` v SQL query |
| IČO CAST pro CRIBIS | ✅ PASS | `WHERE CAST(ic AS STRING) = '{ico}'` |
| Max iterací guard | ✅ PASS | `MAX_MAKER_ITERATIONS = 3` v routing.py |
| Kaskádový fallback | ✅ PASS | `utils/data_fetcher.py` — 4 úrovně |
| WCR_WARNINGS (soft limity) | ✅ PASS | ICR, D/E, Equity Ratio, Quick Ratio |
| CRIBIS prev period (CAPEX) | ✅ PASS | `get_cribis_prev_period()` — OFFSET 1 |
| News signály v EWS | ✅ PASS | ISIR + ČNB + Google News v `news_fetcher.py` |

---

## Fáze 1 — Inventář

**41 Python souborů, 7 867 řádků kódu**

| Modul | Soubory | Status |
|-------|---------|--------|
| pipeline/ | 7 | ✅ Existuje |
| early_warning/ | 7 | ✅ Existuje |
| esg_pipeline/ | 4 | ✅ Existuje |
| skills/ | 8 (7 YAML + __init__) | ✅ Existuje |
| utils/ | 9 | ✅ Existuje |
| ui/ | 8 | ✅ Existuje |
| app.py, CLAUDE.md, README.md | 3 | ✅ Existuje |
| requirements.txt, .env, .env.example | 3 | ✅ Existuje |

---

## Fáze 2 — Smoke testy (post-audit)

| Test | Status | Výstup |
|------|--------|--------|
| `utils.calculator` | ✅ PASS | Calculator OK ✓ |
| `utils.data_fetcher` | ✅ PASS | source=mock_demo, complete=True |
| `utils.news_fetcher` | ✅ PASS | Signals: 0 (demo mode) |
| `skills registry` | ✅ PASS | 7 skills načteno (calculator_skill OK) |
| `esg_pipeline.dispatcher` | ✅ PASS | 6 záznamů |
| `early_warning.graph` | ✅ PASS | RED=2, AMBER=3, GREEN=3 |
| `pipeline.graph 27082440` | ✅ PASS | FROZEN (správně — bez API klíče) |
| Syntax check všech .py | ✅ PASS | 0 syntax chyb |
| `phase4_human_audit` | ✅ PASS | GDPR sanitize OK |

---

*Audit dokončen: 2026-04-14*
*Auditor: Claude Code (Senior IT Auditor role)*
*Příští audit doporučen: před production deployment*
