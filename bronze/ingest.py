# DETERMINISTIC
"""
Bronze Ingest — bronze/ingest.py
Zápis raw dat do Bronze Layer před Silver processing.

Retention: 90 dní "as is" (nezměněná surová data)
Demo: in-memory log (modul-level list)
Prod: INSERT INTO vse_banka.bronze_layer.raw_ingest_log

Každá ingestion event obsahuje:
  - ingest_id (UUID)
  - source (cribis | silver | justice | ares | ews | esg)
  - ico
  - raw_payload (JSON blob)
  - ingest_at (ISO timestamp)
  - pipeline_run_id (pro trasování)
  - schema_valid (bool)
  - auto_fixed (list)

DETERMINISTIC — žádný LLM.
"""
import json
import logging
import os
import uuid
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# In-memory Bronze log (demo mode)
_BRONZE_LOG: list[dict] = []
_MAX_DEMO_ENTRIES = 500   # cap pro demo mode


# DETERMINISTIC
def log_ingest_event(
    source:          str,
    ico:             str,
    raw_payload:     dict,
    pipeline_run_id: str | None = None,
    schema_valid:    bool = True,
    auto_fixed:      list[str] | None = None,
    quarantine_id:   str | None = None,
) -> str:
    """
    Zapíše raw ingest event do Bronze Layer.

    Args:
        source:          Zdrojový systém (cribis | silver | justice | ares | ews | esg)
        ico:             Normalizované IČO
        raw_payload:     Surová data "as is"
        pipeline_run_id: request_id nebo run_id z pipeline
        schema_valid:    Výsledek schema validace
        auto_fixed:      Pole která byla auto-opravena
        quarantine_id:   ID záznamu v karanténě (pokud schema_valid=False)

    Returns:
        ingest_id string
    """
    is_demo = os.getenv("ICM_ENV", "demo").lower() != "production"
    ingest_id = str(uuid.uuid4())[:12]
    now = datetime.now(timezone.utc).isoformat()

    # Serializace payload — omezíme velikost
    try:
        payload_str = json.dumps(raw_payload, ensure_ascii=False, default=str)[:4000]
    except Exception:
        payload_str = str(raw_payload)[:4000]

    entry = {
        "ingest_id":       ingest_id,
        "ingest_at":       now,
        "source":          source,
        "ico":             ico,
        "pipeline_run_id": pipeline_run_id,
        "schema_valid":    schema_valid,
        "auto_fixed":      auto_fixed or [],
        "quarantine_id":   quarantine_id,
        "payload_size":    len(payload_str),
        # raw_payload pouze v demo logu — prod ukládá do Delta table
        "_raw_payload":    raw_payload if is_demo else None,
    }

    if is_demo:
        _BRONZE_LOG.append(entry)
        # Cap pro demo
        if len(_BRONZE_LOG) > _MAX_DEMO_ENTRIES:
            _BRONZE_LOG.pop(0)

        log.debug(
            f"[BronzeIngest] Demo log | ingest_id={ingest_id} "
            f"source={source} ico={ico} valid={schema_valid}"
        )
    else:
        # Prod: INSERT INTO Bronze Delta table
        try:
            from utils.data_connector import query
            auto_str = json.dumps(auto_fixed or [])
            query(f"""
                INSERT INTO vse_banka.bronze_layer.raw_ingest_log
                (ingest_id, ingest_at, source, ico, pipeline_run_id,
                 schema_valid, auto_fixed_json, quarantine_id, payload_size, raw_payload_json)
                VALUES (
                    '{ingest_id}', '{now}', '{source}', '{ico}',
                    '{pipeline_run_id or ""}',
                    {str(schema_valid).lower()},
                    '{auto_str}',
                    '{quarantine_id or ""}',
                    {len(payload_str)},
                    '{payload_str.replace("'", "''")}'
                )
            """)
            log.info(
                f"[BronzeIngest] Prod INSERT | ingest_id={ingest_id} "
                f"source={source} ico={ico}"
            )
        except Exception as exc:
            log.error(f"[BronzeIngest] Prod INSERT selhal — fallback do paměti | {exc}")
            _BRONZE_LOG.append(entry)

    return ingest_id


# DETERMINISTIC
def ingest_with_validation(
    source:          str,
    records:         list[dict],
    pipeline_run_id: str | None = None,
) -> dict:
    """
    Hlavní vstupní bod Bronze Layeru.
    Spustí schema validaci, auto-repair, karanténu a zaloguje každý záznam.

    Returns:
        {
            "clean":            [validní záznamy pro Silver],
            "ingest_ids":       [ingest_id pro každý čistý záznam],
            "quarantined_ids":  [quarantine record_id],
            "auto_fixed_count": int,
            "summary":          str,
        }
    """
    from bronze.quarantine import auto_repair_and_quarantine

    # 1. Validace + auto-repair + karanténa
    repair_result = auto_repair_and_quarantine(records, source)
    clean   = repair_result["clean"]
    q_ids   = repair_result["quarantined_ids"]
    fixed   = repair_result["auto_fixed_count"]

    # 2. Log každého čistého záznamu do Bronze
    ingest_ids = []
    for record in clean:
        ico = str(record.get("ico") or record.get("ic") or "")
        auto_fixed_list = record.pop("_auto_fixed", [])
        iid = log_ingest_event(
            source=source,
            ico=ico,
            raw_payload=record,
            pipeline_run_id=pipeline_run_id,
            schema_valid=True,
            auto_fixed=auto_fixed_list,
        )
        ingest_ids.append(iid)

    # 3. Log karantény (schema_valid=False)
    for qid in q_ids:
        log_ingest_event(
            source=source,
            ico="quarantined",
            raw_payload={},
            pipeline_run_id=pipeline_run_id,
            schema_valid=False,
            quarantine_id=qid,
        )

    summary = (
        f"Bronze ingest: {len(clean)}/{len(records)} OK, "
        f"{len(q_ids)} karanténa, {fixed} auto-opraveno"
    )
    log.info(f"[BronzeIngest] {summary}")

    return {
        "clean":            clean,
        "ingest_ids":       ingest_ids,
        "quarantined_ids":  q_ids,
        "auto_fixed_count": fixed,
        "total":            len(records),
        "summary":          summary,
    }


# DETERMINISTIC
def get_bronze_log(limit: int = 100, source_filter: str | None = None) -> list[dict]:
    """Vrátí záznamy z Bronze logu (demo: in-memory, prod: Databricks)."""
    is_demo = os.getenv("ICM_ENV", "demo").lower() != "production"

    if is_demo:
        records = list(reversed(_BRONZE_LOG))
        if source_filter:
            records = [r for r in records if r.get("source") == source_filter]
        return records[:limit]

    try:
        from utils.data_connector import query
        where = f"AND source = '{source_filter}'" if source_filter else ""
        return query(f"""
            SELECT ingest_id, ingest_at, source, ico,
                   schema_valid, auto_fixed_json, quarantine_id, payload_size
            FROM vse_banka.bronze_layer.raw_ingest_log
            WHERE 1=1 {where}
            ORDER BY ingest_at DESC
            LIMIT {limit}
        """)
    except Exception as exc:
        log.error(f"[BronzeIngest] get_bronze_log prod selhal | {exc}")
        return list(reversed(_BRONZE_LOG))[:limit]


def get_bronze_stats() -> dict:
    """Statistiky Bronze logu pro UI."""
    entries = get_bronze_log(limit=0) if False else list(_BRONZE_LOG)
    total   = len(entries)
    valid   = sum(1 for e in entries if e.get("schema_valid"))
    invalid = total - valid
    sources = {}
    for e in entries:
        s = e.get("source", "unknown")
        sources[s] = sources.get(s, 0) + 1
    return {
        "total":   total,
        "valid":   valid,
        "invalid": invalid,
        "sources": sources,
    }


if __name__ == "__main__":
    # Smoke test
    records = [
        {"ico": "27082440", "company_name": "Stavební holding Praha a.s.", "ebitda": 125000000},
        {"ico": "270 824 40", "company_name": "Auto-fix test", "ebitda": 50000},   # auto-fix
        {"ico": "INVALID", "company_name": "Quarantine test"},                       # karanténa
    ]

    result = ingest_with_validation("test_source", records, pipeline_run_id="REQ-TEST-001")
    print(f"Bronze ingest result: {result['summary']}")
    assert len(result["clean"]) == 2, f"Expected 2 clean, got {len(result['clean'])}"
    assert len(result["quarantined_ids"]) == 1
    assert result["auto_fixed_count"] >= 1

    stats = get_bronze_stats()
    print(f"Bronze stats: {stats}")

    print("OK — bronze/ingest.py smoke test passed")
