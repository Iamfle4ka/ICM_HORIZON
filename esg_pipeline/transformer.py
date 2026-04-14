# DETERMINISTIC + volitelně AI komentář
"""
ESG Transformer — esg_pipeline/transformer.py
Transformuje ESG data pro Tým 5 Cross-Domain Datamart.
NESOUVISÍ s Credit Memo (DP1).
"""
import logging
import os
from datetime import datetime, timezone

log = logging.getLogger(__name__)


def transform_esg(raw_records: list[dict]) -> list[dict]:
    """
    Transformuje raw ESG záznamy pro Cross-Domain Datamart.
    AI komentář přidán pokud ANTHROPIC_API_KEY dostupný.

    Args:
        raw_records: list z collect_esg_data()

    Returns:
        list[dict] připravený pro dispatch
    """
    results = []
    for r in raw_records:
        score = float(r.get("esg_score_raw", 50) or 50)
        flood = str(r.get("flood_risk_raw", "Nízké")).upper()

        # DETERMINISTIC risk kategorizace
        if score < 40:
            risk = "HIGH"
        elif score < 65:
            risk = "MEDIUM"
        else:
            risk = "LOW"

        record = {
            "ico":                   r["ico"],
            "company_name":          r["company_name"],
            "esg_score_normalized":  round(score, 1),
            "flood_risk_category":   flood,
            "esg_risk_summary":      risk,
            "esg_comment":           "",
            "key_factors":           [],
            "transformed_at":        datetime.now(timezone.utc).isoformat(),
            "source":                r.get("source", "unknown"),
        }

        # AI komentář volitelně
        if os.getenv("ANTHROPIC_API_KEY"):
            try:
                record["esg_comment"], record["key_factors"] = _ai_comment(record)
            except Exception as exc:
                log.warning(f"[ESGTransformer] AI comment failed | ico={r['ico']} error={exc}")

        results.append(record)

    log.info(f"[ESGTransformer] Transformováno {len(results)} záznamů")
    return results


def _ai_comment(record: dict) -> tuple[str, list[str]]:
    """AI komentář pro ESG záznam (pro Tým 5, ne Credit Memo)."""
    import json

    import anthropic

    from skills import registry

    skill = registry.get("esg_transformer_skill")
    api_client = anthropic.Anthropic()
    ctx = (
        f"Firma: {record['company_name']} (IČO: {record['ico']})\n"
        f"ESG skóre: {record['esg_score_normalized']}\n"
        f"Flood risk: {record['flood_risk_category']}\n"
        f"Risk summary: {record['esg_risk_summary']}"
    )
    response = api_client.messages.create(
        model="claude-opus-4-6",
        max_tokens=256,
        system=skill["prompt"],
        messages=[{"role": "user", "content": ctx}],
    )
    result = json.loads(response.content[0].text)
    return result.get("esg_comment", ""), result.get("key_factors", [])
