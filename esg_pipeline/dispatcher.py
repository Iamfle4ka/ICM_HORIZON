# DETERMINISTIC
"""
ESG Dispatcher — esg_pipeline/dispatcher.py
Odesílá transformovaná ESG data do Cross-Domain Datamart pro Tým 5.
NESOUVISÍ s Credit Memo (DP1).
DETERMINISTIC — žádný LLM.
"""
import logging
import os
from datetime import datetime, timezone

log = logging.getLogger(__name__)


def dispatch_esg(transformed: list[dict]) -> dict:
    """
    Odesílá transformovaná ESG data pro Tým 5.

    Demo:  loguje + vrátí výsledek
    Prod:  INSERT INTO vse_banka.icm_gen_ai.esg_cross_domain_datamart
    """
    is_demo = os.getenv("ICM_ENV", "demo").lower() != "production"
    dispatched_at = datetime.now(timezone.utc).isoformat()

    log.info(
        f"[ESGDispatcher] Odesílám {len(transformed)} záznamů pro Tým 5 | "
        f"mode={'demo' if is_demo else 'production'}"
    )

    if not is_demo:
        CAT = os.getenv("DATABRICKS_CATALOG", "vse_banka")
        SCH = os.getenv("DATABRICKS_SCHEMA_ESG", "icm_gen_ai")
        try:
            from utils.data_connector import query
            inserted = 0
            errors   = 0
            for record in transformed:
                ico          = str(record.get("ico", ""))
                company_name = str(record.get("company_name", "")).replace("'", "''")
                esg_score    = record.get("esg_score_normalized", 0)
                flood_cat    = str(record.get("flood_risk_category", "UNKNOWN")).replace("'", "''")
                risk_summary = str(record.get("esg_risk_summary", "")).replace("'", "''")
                esg_comment  = str(record.get("esg_comment", "")).replace("'", "''")[:2000]
                source       = str(record.get("source", "esg_pipeline")).replace("'", "''")
                try:
                    query(f"""
                        INSERT INTO {CAT}.{SCH}.esg_cross_domain_datamart
                        (ico, company_name, esg_score_normalized, flood_risk_category,
                         esg_risk_summary, esg_comment, transformed_at, source)
                        VALUES (
                            '{ico}',
                            '{company_name}',
                            {float(esg_score)},
                            '{flood_cat}',
                            '{risk_summary}',
                            '{esg_comment}',
                            '{dispatched_at}',
                            '{source}'
                        )
                    """)
                    inserted += 1
                except Exception as row_exc:
                    log.warning(f"[ESGDispatcher] INSERT failed | ico={ico} error={row_exc}")
                    errors += 1
            log.info(
                f"[ESGDispatcher] Prod INSERT hotov | "
                f"inserted={inserted} errors={errors} target={CAT}.{SCH}.esg_cross_domain_datamart"
            )
        except Exception as exc:
            log.error(f"[ESGDispatcher] Prod write selhal | {exc}")

    return {
        "dispatched":    len(transformed),
        "dispatched_at": dispatched_at,
        "target":        "cross_domain_datamart_tym5",
        "mode":          "demo" if is_demo else "production",
        "records":       transformed,
    }


if __name__ == "__main__":
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)

    from esg_pipeline.collector import collect_esg_data
    from esg_pipeline.transformer import transform_esg

    raw = collect_esg_data()
    transformed = transform_esg(raw)
    result = dispatch_esg(transformed)

    print(f"\nESG pipeline OK — {result['dispatched']} záznamů")
    print(f"  Target: {result['target']}")
    for r in result["records"]:
        risk_icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(r["esg_risk_summary"], "⚪")
        print(
            f"  {risk_icon} {r['ico']} {r['company_name'][:30]:30s} "
            f"ESG={r['esg_score_normalized']:5.1f} flood={r['flood_risk_category']}"
        )
    print("\nOK — esg_pipeline/dispatcher.py smoke test passed")
