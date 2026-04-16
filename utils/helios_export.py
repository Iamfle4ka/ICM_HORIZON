# DETERMINISTIC
"""
Helios / SharePoint Export — utils/helios_export.py
Generuje exportovatelný Credit Memo report z výsledků pipeline.

Formáty:
  - Markdown  (.md)  — primární (čitelné a lehce sdílitelné)
  - Plain text (.txt) — fallback bez markdown

Určen pro:
  - Helios ERP napojení (produkce)
  - SharePoint upload (produkce)
  - Download tlačítko v UI (demo i production)

DETERMINISTIC — žádný LLM.
"""
import logging
import os
from datetime import datetime, timezone

log = logging.getLogger(__name__)


# DETERMINISTIC
def build_markdown_export(pipeline_result: dict) -> str:
    """
    Sestaví Markdown reprezentaci Credit Memo reportu.

    Args:
        pipeline_result: výstup z pipeline.graph.run_pipeline()
            Očekávané klíče: company_name, ico, draft_memo, wcr_report,
                             financial_metrics, citation_coverage, checker_verdict,
                             human_decision (volitelné)

    Returns:
        Markdown string připravený k uložení / downloadu
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    company    = pipeline_result.get("company_name", "N/A")
    ico        = pipeline_result.get("ico", "N/A")
    draft_memo = pipeline_result.get("draft_memo", "")
    wcr_report = pipeline_result.get("wcr_report", {})
    metrics    = pipeline_result.get("financial_metrics", {})
    coverage   = pipeline_result.get("citation_coverage", 0.0)
    checker    = pipeline_result.get("checker_verdict", "N/A")
    decision   = pipeline_result.get("human_decision")

    lines: list[str] = []

    # ── Hlavička ───────────────────────────────────────────────────────────────
    lines += [
        f"# Credit Memo — {company}",
        f"",
        f"| Pole | Hodnota |",
        f"|------|---------|",
        f"| IČO | `{ico}` |",
        f"| Datum exportu | {now} |",
        f"| Citation Coverage | {coverage * 100:.1f} % |",
        f"| Checker verdikt | {checker.upper()} |",
        f"| Generováno systémem | GenAI pro underwriting — Horizon Bank |",
        f"",
    ]

    # ── Rozhodnutí underwritera ────────────────────────────────────────────────
    if decision:
        dec_map = {
            "approve":                  "✅ SCHVÁLENO",
            "reject":                   "❌ ZAMÍTNUTO",
            "approve_with_conditions":  "⚠️ PODMÍNEČNĚ SCHVÁLENO",
        }
        dec_label = dec_map.get(decision.get("decision", ""), decision.get("decision", ""))
        lines += [
            f"## Rozhodnutí underwritera",
            f"",
            f"**{dec_label}**",
            f"",
        ]
        if decision.get("decided_by"):
            lines.append(f"- Rozhodl: `{decision['decided_by']}`")
        if decision.get("decided_at"):
            lines.append(f"- Čas: {decision['decided_at']}")
        if decision.get("comments"):
            lines.append(f"- Komentář: {decision['comments']}")
        lines.append("")

    # ── Text mema ─────────────────────────────────────────────────────────────
    lines += [
        f"## Credit Memo",
        f"",
    ]
    if draft_memo:
        # Odstraníme citation tagy pro čistý export
        clean_memo = draft_memo.replace("[CITATION:", "[zdroj:").replace("]", "]")
        lines.append(clean_memo)
    else:
        lines.append("_Memo není k dispozici._")
    lines.append("")

    # ── WCR Report ─────────────────────────────────────────────────────────────
    lines += [
        f"## WCR Report (Working Capital Rules)",
        f"",
    ]
    rules = wcr_report.get("rules", [])
    if rules:
        lines += [
            f"| Pravidlo | Hodnota | Limit | Status |",
            f"|----------|---------|-------|--------|",
        ]
        for rule in rules:
            passed  = rule.get("passed")
            skipped = rule.get("skipped", False)
            val     = rule.get("value")
            unit    = rule.get("unit", "")
            limit   = rule.get("limit", "N/A")
            desc    = rule.get("description", rule.get("name", ""))

            if skipped or passed is None:
                status  = "⏭️ N/A"
                val_str = "N/A"
            elif passed:
                status  = "✅ PASS"
                val_str = f"{val}{unit}" if val is not None else "N/A"
            else:
                status  = "❌ FAIL"
                val_str = f"{val}{unit}" if val is not None else "N/A"

            lines.append(f"| {desc} | {val_str} | {limit}{unit} | {status} |")

        summary = wcr_report.get("summary", {})
        breaches = wcr_report.get("breaches", [])
        overall = "✅ PASS" if wcr_report.get("passed", True) else f"❌ FAIL ({len(breaches)} porušení)"
        lines += ["", f"**Celkový WCR status: {overall}**", ""]

        if breaches:
            lines += ["**Porušení:**", ""]
            for b in breaches:
                lines.append(f"- {b}")
            lines.append("")
    else:
        lines.append("_WCR report není k dispozici._\n")

    # ── Finanční metriky ───────────────────────────────────────────────────────
    if metrics:
        lines += [
            f"## Finanční metriky",
            f"",
            f"| Metrika | Hodnota |",
            f"|---------|---------|",
        ]
        metric_labels = {
            "dscr":            "DSCR (CAPEX-adj.)",
            "leverage_ratio":  "Leverage Ratio (Net Debt / EBITDA)",
            "current_ratio":   "Current Ratio",
            "utilisation_pct": "Využití limitu (%)",
            "icr":             "ICR (EBITDA / Úroky)",
            "de_ratio":        "D/E Ratio",
            "equity_ratio":    "Equity Ratio (%)",
            "quick_ratio":     "Quick Ratio",
        }
        for key, label in metric_labels.items():
            val = metrics.get(key)
            if val is not None:
                if isinstance(val, float):
                    lines.append(f"| {label} | {val:.3f} |")
                else:
                    lines.append(f"| {label} | {val} |")
        lines.append("")

    # ── Patička ────────────────────────────────────────────────────────────────
    lines += [
        f"---",
        f"",
        f"*Dokument vygenerován automaticky systémem GenAI pro underwriting (Horizon Bank).*  ",
        f"*AI-asistovaný výstup — finální rozhodnutí závisí na schválení underwritera (4-Eyes Rule).*  ",
        f"*Export: {now}*",
    ]

    return "\n".join(lines)


# DETERMINISTIC
def build_text_export(pipeline_result: dict) -> str:
    """
    Plain text verze exportu (bez Markdown formátování).
    Použije build_markdown_export a odstraní Markdown syntax.
    """
    md = build_markdown_export(pipeline_result)
    # Odstraní Markdown hlavičky, tabulky, tučné písmo
    import re
    text = re.sub(r"^#{1,6}\s+", "", md, flags=re.MULTILINE)  # headings
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)               # bold
    text = re.sub(r"\*(.*?)\*", r"\1", text)                    # italic
    text = re.sub(r"\|.*?\|", "", text)                         # tables
    text = re.sub(r"^\s*\|[-| :]+\|\s*$", "", text, flags=re.MULTILINE)  # table separators
    text = re.sub(r"\n{3,}", "\n\n", text)                      # triple newlines
    return text.strip()


# DETERMINISTIC
def export_to_helios(pipeline_result: dict, run_id: str | None = None) -> dict:
    """
    Odesílá Credit Memo do Helios ERP.

    Demo:  loguje + vrátí výsledek
    Prod:  POST na Helios REST API endpoint

    Args:
        pipeline_result: výstup z pipeline
        run_id:          volitelné ID runu pro trasování

    Returns:
        {"success": bool, "helios_doc_id": str|None, "export_at": str, "mode": str}
    """
    is_demo = os.getenv("ICM_ENV", "demo").lower() != "production"
    export_at = datetime.now(timezone.utc).isoformat()
    company   = pipeline_result.get("company_name", "N/A")
    ico       = pipeline_result.get("ico", "N/A")

    md_content = build_markdown_export(pipeline_result)

    log.info(
        f"[HeliosExport] Exportuji memo | ico={ico} company={company} "
        f"run_id={run_id} mode={'demo' if is_demo else 'production'} "
        f"content_len={len(md_content)}"
    )

    if is_demo:
        return {
            "success":       True,
            "helios_doc_id": None,
            "export_at":     export_at,
            "mode":          "demo",
            "content_len":   len(md_content),
        }

    # Production: POST na Helios API
    helios_url    = os.getenv("HELIOS_API_URL", "")
    helios_token  = os.getenv("HELIOS_API_TOKEN", "")

    if not helios_url or not helios_token:
        log.error("[HeliosExport] Chybí HELIOS_API_URL nebo HELIOS_API_TOKEN")
        return {
            "success":       False,
            "helios_doc_id": None,
            "export_at":     export_at,
            "mode":          "production",
            "error":         "Chybí Helios API konfigurace",
        }

    try:
        import urllib.request, json as _json
        payload = _json.dumps({
            "document_type": "credit_memo",
            "ico":           ico,
            "company_name":  company,
            "run_id":        run_id or "",
            "content_md":    md_content,
            "exported_at":   export_at,
        }).encode("utf-8")

        req = urllib.request.Request(
            helios_url,
            data=payload,
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {helios_token}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp_data = _json.loads(resp.read().decode("utf-8"))
            doc_id = resp_data.get("document_id") or resp_data.get("id")

        log.info(f"[HeliosExport] Prod POST OK | doc_id={doc_id} ico={ico}")
        return {
            "success":       True,
            "helios_doc_id": doc_id,
            "export_at":     export_at,
            "mode":          "production",
        }

    except Exception as exc:
        log.error(f"[HeliosExport] Prod POST selhal | ico={ico} error={exc}")
        return {
            "success":       False,
            "helios_doc_id": None,
            "export_at":     export_at,
            "mode":          "production",
            "error":         str(exc),
        }


# DETERMINISTIC
def get_download_bytes(pipeline_result: dict, fmt: str = "md") -> tuple[bytes, str, str]:
    """
    Vrátí (bytes, filename, mime_type) pro Streamlit st.download_button().

    Args:
        pipeline_result: výstup pipeline
        fmt:             "md" nebo "txt"

    Returns:
        (content_bytes, filename, mime_type)
    """
    import re as _re
    ico       = pipeline_result.get("ico", "unknown")
    company   = pipeline_result.get("company_name", "memo")
    safe_name = _re.sub(r"[^\w\-]", "_", company)[:30]
    date_str  = datetime.now().strftime("%Y%m%d")

    if fmt == "txt":
        content  = build_text_export(pipeline_result)
        filename = f"credit_memo_{ico}_{safe_name}_{date_str}.txt"
        mime     = "text/plain"
    else:
        content  = build_markdown_export(pipeline_result)
        filename = f"credit_memo_{ico}_{safe_name}_{date_str}.md"
        mime     = "text/markdown"

    return content.encode("utf-8"), filename, mime


if __name__ == "__main__":
    # Smoke test
    mock_result = {
        "ico":              "27082440",
        "company_name":     "Stavební holding Praha a.s.",
        "draft_memo":       "Klient vykazuje stabilní finanční profil. [CITATION:cribis_external]\n\nDSCR = 1.45x, využití limitu 62 %.",
        "citation_coverage": 0.92,
        "checker_verdict":  "approved",
        "wcr_report": {
            "passed": True,
            "breaches": [],
            "rules": [
                {"description": "DSCR", "passed": True,  "value": 1.45, "limit": 1.2, "unit": "x"},
                {"description": "Využití limitu", "passed": True, "value": 62.0, "limit": 85, "unit": "%"},
                {"description": "Leverage Ratio", "passed": None, "skipped": True, "note": "Čeká na CRIBIS"},
            ],
        },
        "financial_metrics": {
            "dscr": 1.45, "leverage_ratio": 3.2, "current_ratio": 1.8, "utilisation_pct": 62.0,
        },
        "human_decision": {
            "decision": "approve", "decided_by": "underwriter_test",
            "decided_at": "2026-04-15T10:00:00Z", "comments": "Dobrý klient.",
        },
    }

    md = build_markdown_export(mock_result)
    assert "Stavební holding Praha a.s." in md
    assert "DSCR" in md
    assert "✅ PASS" in md
    assert "⏭️ N/A" in md
    print(f"  build_markdown_export: OK ({len(md)} chars)")

    txt = build_text_export(mock_result)
    assert "DSCR" in txt
    print(f"  build_text_export: OK ({len(txt)} chars)")

    content, fname, mime = get_download_bytes(mock_result, "md")
    assert fname.startswith("credit_memo_27082440")
    assert mime == "text/markdown"
    print(f"  get_download_bytes md: OK fname={fname}")

    content2, fname2, mime2 = get_download_bytes(mock_result, "txt")
    assert mime2 == "text/plain"
    print(f"  get_download_bytes txt: OK fname={fname2}")

    result = export_to_helios(mock_result, run_id="REQ-TEST-001")
    assert result["success"] is True
    assert result["mode"] == "demo"
    print(f"  export_to_helios demo: OK {result}")

    print("OK — utils/helios_export.py smoke test passed")
