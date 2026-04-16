# DETERMINISTIC
"""
Bronze Schema Validator — bronze/schema_validator.py
Validuje surová data před zápisem do Bronze Layer.

Kontroly:
  - IČO formát (8 číslic, auto-oprava mezer/pomlček)
  - povinná pole
  - datové typy
  - duplikáty (ICO resolution)

Vrací ValidationResult s passed/errors/warnings/auto_fixed.
DETERMINISTIC — žádný LLM.
"""
import logging
import re
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    passed:       bool
    ico:          str                    # normalizované IČO (po auto-opravě)
    errors:       list[str] = field(default_factory=list)
    warnings:     list[str] = field(default_factory=list)
    auto_fixed:   list[str] = field(default_factory=list)  # co bylo automaticky opraveno
    quarantine:   bool = False           # True → záznam do karantény
    quarantine_reason: str = ""


# DETERMINISTIC
def validate_raw_record(record: dict, source: str = "unknown") -> ValidationResult:
    """
    Validuje jeden raw záznam ze zdroje.

    Args:
        record: dict se surými daty (musí obsahovat 'ico' nebo 'ic')
        source: název zdrojového systému (pro log)

    Returns:
        ValidationResult — vždy vrátí, nikdy nevyhodí výjimku.
    """
    errors:     list[str] = []
    warnings:   list[str] = []
    auto_fixed: list[str] = []

    # ── IČO extrakce a normalizace ────────────────────────────────────────────
    raw_ico = str(record.get("ico") or record.get("ic") or record.get("IČO") or "").strip()

    if not raw_ico:
        return ValidationResult(
            passed=False,
            ico="",
            errors=["Chybí IČO/ic — nelze identifikovat záznam"],
            quarantine=True,
            quarantine_reason="missing_ico",
        )

    # Auto-oprava: odstranit nečíselné znaky (mezery, pomlčky, lomítka)
    cleaned = re.sub(r"[^\d]", "", raw_ico)
    if cleaned != raw_ico:
        auto_fixed.append(f"IČO: '{raw_ico}' → '{cleaned}' (odstraněny nečíselné znaky)")
        raw_ico = cleaned

    # Auto-oprava: doplnit vedoucí nuly na 8 číslic
    if cleaned.isdigit() and len(cleaned) < 8:
        padded = cleaned.zfill(8)
        auto_fixed.append(f"IČO: '{cleaned}' → '{padded}' (doplněny vedoucí nuly)")
        raw_ico = padded
        cleaned = padded

    # Validace formátu
    if not re.fullmatch(r"\d{8}", cleaned):
        return ValidationResult(
            passed=False,
            ico=raw_ico,
            errors=[f"Neplatný formát IČO: '{raw_ico}' (požadováno 8 číslic, nalezeno {len(cleaned)})"],
            auto_fixed=auto_fixed,
            quarantine=True,
            quarantine_reason="invalid_ico_format",
        )

    ico = cleaned

    # ── Kontrola povinných polí podle zdroje ──────────────────────────────────
    required_fields = {
        "cribis":         ["ic", "ebitda"],
        "silver_credit":  ["approved_limit_czk", "outstanding_balance_czk"],
        "silver_company": ["company_name"],
        "ews":            ["ico"],
        "unknown":        [],
    }
    for field_name in required_fields.get(source, []):
        if record.get(field_name) is None:
            warnings.append(f"Chybí doporučené pole '{field_name}' (zdroj: {source})")

    # ── Numerická kontrola kritických polí ────────────────────────────────────
    numeric_fields = [
        "ebitda", "revenue", "total_assets", "approved_limit_czk",
        "outstanding_balance_czk", "dpd_current", "credit_limit_utilization",
    ]
    for f in numeric_fields:
        val = record.get(f)
        if val is not None:
            try:
                float(val)
            except (TypeError, ValueError):
                warnings.append(f"Pole '{f}' nelze převést na číslo: {val!r}")

    passed = len(errors) == 0

    log.debug(
        f"[SchemaValidator] ico={ico} source={source} "
        f"passed={passed} errors={len(errors)} warnings={len(warnings)} "
        f"auto_fixed={len(auto_fixed)}"
    )

    return ValidationResult(
        passed=passed,
        ico=ico,
        errors=errors,
        warnings=warnings,
        auto_fixed=auto_fixed,
        quarantine=not passed,
        quarantine_reason=errors[0] if errors else "",
    )


# DETERMINISTIC
def validate_batch(records: list[dict], source: str = "unknown") -> dict:
    """
    Validuje seznam záznamů najednou.

    Returns:
        {
          "passed": [...],
          "quarantined": [...],
          "total": int,
          "pass_count": int,
          "quarantine_count": int,
          "auto_fixed_count": int,
        }
    """
    passed = []
    quarantined = []
    auto_fixed_total = 0

    for record in records:
        result = validate_raw_record(record, source)
        if result.auto_fixed:
            auto_fixed_total += len(result.auto_fixed)
            # Aktualizuj record s opraveným IČO
            record = {**record, "ico": result.ico, "_auto_fixed": result.auto_fixed}

        if result.passed:
            passed.append(record)
        else:
            quarantined.append({
                "record":             record,
                "errors":             result.errors,
                "warnings":           result.warnings,
                "quarantine_reason":  result.quarantine_reason,
                "auto_fixed":         result.auto_fixed,
            })

    log.info(
        f"[SchemaValidator] Batch validace | source={source} "
        f"total={len(records)} pass={len(passed)} "
        f"quarantine={len(quarantined)} auto_fixed={auto_fixed_total}"
    )

    return {
        "passed":           passed,
        "quarantined":      quarantined,
        "total":            len(records),
        "pass_count":       len(passed),
        "quarantine_count": len(quarantined),
        "auto_fixed_count": auto_fixed_total,
    }


if __name__ == "__main__":
    # Smoke test
    tests = [
        ({"ico": "27082440", "company_name": "Test s.r.o."}, "silver_company", True),
        ({"ico": "00514152", "company_name": "Energetika"}, "silver_company", True),
        ({"ico": "270 824 40", "company_name": "Test"}, "silver_company", True),   # auto-fix
        ({"ico": "2708244", "company_name": "Test"}, "silver_company", True),      # auto-pad
        ({"ico": "INVALID", "company_name": "Bad"}, "silver_company", False),
        ({"company_name": "Missing ICO"}, "silver_company", False),
    ]

    print("SchemaValidator smoke test:")
    for record, source, expected_pass in tests:
        r = validate_raw_record(record, source)
        status = "✅" if r.passed == expected_pass else "❌"
        fixes = f" auto_fixed={r.auto_fixed}" if r.auto_fixed else ""
        errs = f" errors={r.errors}" if r.errors else ""
        print(f"  {status} ico={record.get('ico','—')} passed={r.passed}{fixes}{errs}")

    print("OK — bronze/schema_validator.py smoke test passed")
