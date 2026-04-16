# DETERMINISTIC
"""
PII Masker — utils/pii_masker.py
Maskuje osobní údaje (PII) před zápisem do Silver Layer a Audit Trail.

Maskované typy:
  - Telefonní čísla (CZ formáty)
  - E-mailové adresy
  - Rodná čísla (YYMMDD/NNNN)
  - Čísla bankovních účtů (předčíslí-čísloúčtu/kód)
  - IBANy
  - Jména (heuristika: Jméno Příjmení)

DETERMINISTIC — žádný LLM.
"""
import logging
import re
from typing import Any

log = logging.getLogger(__name__)

# ── Regex vzory ────────────────────────────────────────────────────────────────

# Telefonní čísla: +420 NNN NNN NNN, 420NNNNNNNNN, 0NNN NNN NNN
_RE_PHONE = re.compile(
    r"(?<!\d)(\+?420[\s\-]?)?(\d{3}[\s\-]?\d{3}[\s\-]?\d{3})(?!\d)"
)

# E-maily
_RE_EMAIL = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)

# Rodné číslo: 6-místné číslo / 4-místné číslo (s lomítkem nebo bez)
_RE_RC = re.compile(
    r"\b(\d{6})/?(\d{4})\b"
)

# Bankovní účet: (předčíslí-)čísloúčtu/kód_banky
_RE_BANK_ACCOUNT = re.compile(
    r"\b(\d{1,6}-)?\d{6,10}/\d{4}\b"
)

# IBAN: CZ + 22 alfanumerických znaků
_RE_IBAN = re.compile(
    r"\bCZ\d{2}[ ]?(\d{4}[ ]?){4,5}\b"
)

# Jména (heuristika: dvě kapitalizovaná slova, min 3 znaky každé)
# Pouze na explicitní request (může být too aggressive pro firemní data)
_RE_NAME = re.compile(
    r"\b([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][a-záčďéěíňóřšťúůýž]{2,})\s+([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][a-záčďéěíňóřšťúůýž]{2,})\b"
)


# DETERMINISTIC
def mask_text(
    text: str,
    mask_phones: bool = True,
    mask_emails: bool = True,
    mask_rc: bool = True,
    mask_bank: bool = True,
    mask_iban: bool = True,
    mask_names: bool = False,   # Off by default — příliš agresivní pro firemní data
) -> str:
    """
    Maskuje PII v textu. Vrátí nový string s nahrazenými hodnotami.

    Args:
        text:        Vstupní text
        mask_phones: Maskovat telefonní čísla
        mask_emails: Maskovat e-maily
        mask_rc:     Maskovat rodná čísla
        mask_bank:   Maskovat bankovní účty
        mask_iban:   Maskovat IBANy
        mask_names:  Maskovat jména (heuristika, off by default)

    Returns:
        Maskovaný text
    """
    if not text or not isinstance(text, str):
        return text

    original_len = len(text)
    masked_count = 0

    if mask_iban:
        new_text, n = _RE_IBAN.subn("[IBAN_MASKED]", text)
        if n:
            log.debug(f"[PIIMasker] Maskováno {n} IBAN(ů)")
            masked_count += n
        text = new_text

    if mask_bank:
        new_text, n = _RE_BANK_ACCOUNT.subn("[BANK_ACCOUNT_MASKED]", text)
        if n:
            log.debug(f"[PIIMasker] Maskováno {n} bankovní účet(y)")
            masked_count += n
        text = new_text

    if mask_rc:
        new_text, n = _RE_RC.subn("[RC_MASKED]", text)
        if n:
            log.debug(f"[PIIMasker] Maskováno {n} rodné číslo/čísla")
            masked_count += n
        text = new_text

    if mask_emails:
        new_text, n = _RE_EMAIL.subn("[EMAIL_MASKED]", text)
        if n:
            log.debug(f"[PIIMasker] Maskováno {n} e-mail(ů)")
            masked_count += n
        text = new_text

    if mask_phones:
        new_text, n = _RE_PHONE.subn("[PHONE_MASKED]", text)
        if n:
            log.debug(f"[PIIMasker] Maskováno {n} telefonní číslo/čísla")
            masked_count += n
        text = new_text

    if mask_names:
        new_text, n = _RE_NAME.subn("[NAME_MASKED]", text)
        if n:
            log.debug(f"[PIIMasker] Maskováno {n} jméno/jmen")
            masked_count += n
        text = new_text

    if masked_count:
        log.info(
            f"[PIIMasker] mask_text | original_len={original_len} "
            f"masked_items={masked_count}"
        )

    return text


# DETERMINISTIC
def mask_dict(
    data: dict,
    fields_to_mask: list[str] | None = None,
    mask_all_strings: bool = False,
    **kwargs: bool,
) -> dict:
    """
    Maskuje PII ve slovníku. Rekurzivně zpracuje vnořené dict/list.

    Args:
        data:             Vstupní slovník
        fields_to_mask:   Seznam klíčů k maskování (pokud None + mask_all_strings=False,
                          maskuje pouze pole s PII klíčovými slovy)
        mask_all_strings: Pokud True, maskuje všechny string hodnoty
        **kwargs:         Předány do mask_text (mask_phones, mask_emails, atd.)

    Returns:
        Nový dict s maskovanými hodnotami (originál nezměněn)
    """
    # Klíčová slova označující PII pole
    _PII_FIELD_KEYWORDS = {
        "phone", "tel", "email", "mail", "rc", "rodne_cislo",
        "birth", "contact", "kontakt", "person", "osoba",
        "account", "ucet", "iban", "name", "jmeno", "prijmeni",
        "address", "adresa",
    }

    result = {}
    for key, value in data.items():
        should_mask = (
            mask_all_strings
            or (fields_to_mask is not None and key in fields_to_mask)
            or (
                fields_to_mask is None
                and any(kw in key.lower() for kw in _PII_FIELD_KEYWORDS)
            )
        )

        if isinstance(value, dict):
            result[key] = mask_dict(value, fields_to_mask, mask_all_strings, **kwargs)
        elif isinstance(value, list):
            result[key] = [
                mask_dict(item, fields_to_mask, mask_all_strings, **kwargs)
                if isinstance(item, dict)
                else (mask_text(item, **kwargs) if isinstance(item, str) and should_mask else item)
                for item in value
            ]
        elif isinstance(value, str) and should_mask:
            result[key] = mask_text(value, **kwargs)
        else:
            result[key] = value

    return result


# DETERMINISTIC
def mask_audit_entry(entry: dict) -> dict:
    """
    Maskuje PII v audit trail záznamu.
    Bezpečně odstraní citlivé hodnoty ale zachová strukturu.

    Maskuje: metadata.comments, metadata.reviewer_note, metadata.fallback_reason
    """
    masked = dict(entry)

    meta = entry.get("metadata", {})
    if meta:
        masked["metadata"] = mask_dict(
            meta,
            fields_to_mask=["comments", "reviewer_note", "fallback_reason", "note"],
            mask_all_strings=False,
        )

    return masked


if __name__ == "__main__":
    # Smoke test
    tests = [
        # (vstup, klíčové slovo které MUSÍ být maskováno)
        ("Kontakt: jan.novak@citi.com, tel: +420 603 123 456", "[EMAIL_MASKED]"),
        ("Rodné číslo: 850101/1234 a také 9001021234", "[RC_MASKED]"),
        ("Bankovní účet: 123456-0987654321/0300", "[BANK_ACCOUNT_MASKED]"),
        ("IBAN: CZ65 0800 0000 1920 0014 5399", "[IBAN_MASKED]"),
        ("tel 603123456 nebo 00420603123456", "[PHONE_MASKED]"),
    ]

    print("PII Masker smoke test:")
    all_ok = True
    for text, expected_token in tests:
        result = mask_text(text)
        ok = expected_token in result
        status = "✅" if ok else "❌"
        if not ok:
            all_ok = False
        print(f"  {status} '{text[:40]}...' → contains '{expected_token}': {ok}")
        if not ok:
            print(f"       result: {result}")

    # Dict masking
    data = {
        "ico": "27082440",
        "company_name": "Test s.r.o.",
        "contact_email": "director@test.cz",
        "phone": "+420 777 888 999",
        "revenue": 125000000,
    }
    masked = mask_dict(data)
    assert masked["ico"] == "27082440", "ICO nesmí být maskováno"
    assert "[EMAIL_MASKED]" in masked["contact_email"], "E-mail musí být maskován"
    assert "[PHONE_MASKED]" in masked["phone"], "Telefon musí být maskován"
    assert masked["revenue"] == 125000000, "Revenue nesmí být maskováno"
    print("  ✅ mask_dict: ICO zachováno, e-mail/telefon maskovány, revenue zachováno")

    assert all_ok, "Některé testy selhaly!"
    print("OK — utils/pii_masker.py smoke test passed")
