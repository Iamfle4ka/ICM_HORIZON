# DETERMINISTIC
"""
Quarantine Zone — bronze/quarantine.py
Spravuje záznamy které selhaly při DQ validaci.

Funkce:
  quarantine_record(record, reason, source)  → uloží do karantény
  get_quarantine()                           → seznam čekajících záznamů
  release_record(record_id)                  → schválí Data Steward, přesune do Silver
  reject_record(record_id, reason)           → trvale odmítne + zaloguje
  auto_repair_batch(records)                 → pokusí se auto-opravit

Persistence:
  Demo:  in-memory (session-level, Streamlit session_state nebo modul-level dict)
  Prod:  INSERT/SELECT z vse_banka.bronze_layer.quarantine_zone

DETERMINISTIC — žádný LLM.
"""
import logging
import os
import uuid
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# ── In-memory store pro demo mode ─────────────────────────────────────────────
# V prod mode by to byl Databricks Delta table
_QUARANTINE_STORE: dict[str, dict] = {}


# DETERMINISTIC
def quarantine_record(
    record:  dict,
    reason:  str,
    source:  str = "unknown",
    errors:  list[str] | None = None,
    auto_fixed: list[str] | None = None,
) -> str:
    """
    Uloží záznam do Quarantine Zone.

    Args:
        record:     Původní raw záznam
        reason:     Důvod karantény (z ValidationResult.quarantine_reason)
        source:     Zdrojový systém
        errors:     Seznam chyb z validace
        auto_fixed: Co bylo auto-opraveno před karanténou

    Returns:
        record_id (UUID string) pro pozdější release/reject
    """
    is_demo = os.getenv("ICM_ENV", "demo").lower() != "production"
    record_id = str(uuid.uuid4())[:12]
    now = datetime.now(timezone.utc).isoformat()

    entry = {
        "record_id":    record_id,
        "quarantined_at": now,
        "source":       source,
        "reason":       reason,
        "errors":       errors or [],
        "auto_fixed":   auto_fixed or [],
        "record":       record,
        "status":       "pending",    # pending | released | rejected
        "reviewed_by":  None,
        "reviewed_at":  None,
        "review_note":  None,
    }

    if is_demo:
        _QUARANTINE_STORE[record_id] = entry
        log.info(
            f"[Quarantine] Záznam uložen | record_id={record_id} "
            f"source={source} reason={reason}"
        )
    else:
        # Prod: INSERT INTO bronze_layer.quarantine_zone
        try:
            from utils.data_connector import query
            ico = str(record.get("ico") or record.get("ic") or "")
            query(f"""
                INSERT INTO vse_banka.bronze_layer.quarantine_zone
                (record_id, quarantined_at, source, reason, errors_json,
                 raw_record_json, status)
                VALUES (
                    '{record_id}', '{now}', '{source}',
                    '{reason}',
                    '{str(errors or [])}',
                    '{str(record)[:2000]}',
                    'pending'
                )
            """)
            log.info(f"[Quarantine] Prod: INSERT quarantine_zone | record_id={record_id} ico={ico}")
        except Exception as exc:
            log.error(f"[Quarantine] Prod INSERT selhal — fallback do paměti | {exc}")
            _QUARANTINE_STORE[record_id] = entry

    return record_id


# DETERMINISTIC
def get_quarantine(status_filter: str | None = "pending") -> list[dict]:
    """
    Vrátí záznamy z Quarantine Zone.

    Args:
        status_filter: "pending" | "released" | "rejected" | None (vše)
    """
    is_demo = os.getenv("ICM_ENV", "demo").lower() != "production"

    if is_demo:
        records = list(_QUARANTINE_STORE.values())
    else:
        try:
            from utils.data_connector import query
            where = f"WHERE status = '{status_filter}'" if status_filter else ""
            rows = query(f"""
                SELECT record_id, quarantined_at, source, reason,
                       errors_json, status, reviewed_by, reviewed_at, review_note
                FROM vse_banka.bronze_layer.quarantine_zone
                {where}
                ORDER BY quarantined_at DESC
                LIMIT 200
            """)
            records = rows
        except Exception as exc:
            log.error(f"[Quarantine] Prod SELECT selhal — fallback | {exc}")
            records = list(_QUARANTINE_STORE.values())

    if status_filter:
        records = [r for r in records if r.get("status") == status_filter]

    return sorted(records, key=lambda r: r.get("quarantined_at", ""), reverse=True)


# DETERMINISTIC
def release_record(record_id: str, reviewed_by: str = "data_steward", note: str = "") -> bool:
    """
    Data Steward schválí záznam → uvolní z karantény do Silver.
    Vrátí True pokud nalezen a uvolněn.
    """
    now = datetime.now(timezone.utc).isoformat()

    if record_id in _QUARANTINE_STORE:
        _QUARANTINE_STORE[record_id].update({
            "status":       "released",
            "reviewed_by":  reviewed_by,
            "reviewed_at":  now,
            "review_note":  note,
        })
        log.info(f"[Quarantine] Uvolněn | record_id={record_id} by={reviewed_by}")
        return True

    log.warning(f"[Quarantine] record_id={record_id} nenalezen pro release")
    return False


# DETERMINISTIC
def reject_record(record_id: str, reviewed_by: str = "data_steward", reason: str = "") -> bool:
    """
    Data Steward trvale odmítne záznam. Zůstane v logu pro audit.
    """
    now = datetime.now(timezone.utc).isoformat()

    if record_id in _QUARANTINE_STORE:
        _QUARANTINE_STORE[record_id].update({
            "status":       "rejected",
            "reviewed_by":  reviewed_by,
            "reviewed_at":  now,
            "review_note":  reason,
        })
        log.info(f"[Quarantine] Odmítnut | record_id={record_id} by={reviewed_by} reason={reason}")
        return True

    return False


# DETERMINISTIC
def get_quarantine_summary() -> dict:
    """Vrátí souhrn statistik karantény."""
    all_records = get_quarantine(status_filter=None)
    return {
        "total":    len(all_records),
        "pending":  sum(1 for r in all_records if r.get("status") == "pending"),
        "released": sum(1 for r in all_records if r.get("status") == "released"),
        "rejected": sum(1 for r in all_records if r.get("status") == "rejected"),
        "sources":  list({r.get("source", "unknown") for r in all_records}),
        "reasons":  list({r.get("reason", "") for r in all_records}),
    }


# DETERMINISTIC
def auto_repair_and_quarantine(records: list[dict], source: str) -> dict:
    """
    Spustí schema validaci na batch, auto-opraví co lze,
    karantény co nelze. Vrátí clean records pro Silver.

    Returns:
        {
            "clean": [records připravené pro Silver],
            "quarantined_ids": [record_id stringy],
            "auto_fixed_count": int,
        }
    """
    from bronze.schema_validator import validate_batch

    result = validate_batch(records, source)
    quarantined_ids = []

    for entry in result["quarantined"]:
        rid = quarantine_record(
            record=entry["record"],
            reason=entry["quarantine_reason"],
            source=source,
            errors=entry["errors"],
            auto_fixed=entry["auto_fixed"],
        )
        quarantined_ids.append(rid)

    log.info(
        f"[Quarantine] auto_repair_and_quarantine | source={source} "
        f"clean={len(result['passed'])} quarantined={len(quarantined_ids)} "
        f"auto_fixed={result['auto_fixed_count']}"
    )

    return {
        "clean":             result["passed"],
        "quarantined_ids":   quarantined_ids,
        "auto_fixed_count":  result["auto_fixed_count"],
        "quarantine_count":  len(quarantined_ids),
    }


# ── Inicializace demo dat ──────────────────────────────────────────────────
is_demo = os.getenv("ICM_ENV", "demo").lower() != "production"
if is_demo and not _QUARANTINE_STORE:
    quarantine_record(
        record={"company_name": "Pandora Fashion Group s.r.o.", "ico": "10201512", "ebitda": "-5000000"},
        reason="invalid_metric_value",
        source="cribis",
        errors=["CRIBIS EBITDA je záporná (-5 000 000), automatika vyžaduje potvrzení Stewartem."],
    )
    quarantine_record(
        record={"company_name": "Agro Future s.r.o.", "ico": "10201108", "datum_vzniku": "31-02-2015"},
        reason="date_parsing_error",
        source="ares",
        errors=["Neplatný formát data vzniku: '31-02-2015' (neexistující datum)."],
    )
    quarantine_record(
        record={"ico": "10200401", "company_name": "EkoStav Holding s.r.o.", "net_debt": "N/A"},
        reason="missing_critical_financials",
        source="cbs",
        errors=["Chybí hodnota Net Debt v účetních výkazech, nelze spočítat Leverage Ratio."],
        auto_fixed=["IČO normalizováno ('1020 0401' → '10200401')"],
    )
    quarantine_record(
        record={"ico": "10200300", "company_name": "Quantum Dynamics", "status": "V likvidaci"},
        reason="company_in_liquidation",
        source="justice_cz",
        errors=["Společnost vstoupila do likvidace dle OR Justice.cz. Rizikový status."],
        auto_fixed=["Název normalizován: odstraněny neviditelné znaky."],
    )
    quarantine_record(
        record={"ico": "10201111", "company_name": "Velkopivovar Morava a.s.", "dpd": 450},
        reason="extreme_outlier",
        source="ews_internal",
        errors=["DPD = 450 dní překračuje logické prahy pro nového žadatele. Možná chyba databázového propojení."],
    )


if __name__ == "__main__":
    # Smoke test
    rid1 = quarantine_record(
        {"ico": "INVALID", "company": "Bad Corp"},
        reason="invalid_ico_format",
        source="cribis",
        errors=["Neplatný formát IČO"],
    )
    rid2 = quarantine_record(
        {"company": "Missing ICO Corp"},
        reason="missing_ico",
        source="silver_company",
    )

    pending = get_quarantine("pending")
    assert len(pending) == 2, f"Expected 2 pending, got {len(pending)}"

    release_record(rid1, reviewed_by="data_steward_test", note="Manuálně opraveno")
    reject_record(rid2, reviewed_by="data_steward_test", reason="Duplikát")

    summary = get_quarantine_summary()
    assert summary["released"] == 1
    assert summary["rejected"] == 1
    assert summary["pending"] == 0

    print(f"Quarantine summary: {summary}")
    print("OK — bronze/quarantine.py smoke test passed")
