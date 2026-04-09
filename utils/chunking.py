"""
Semantic Chunking — utils/chunking.py
Dělí dokumenty podle smyslu, NE po stránkách nebo pevné délce.
DETERMINISTIC — žádný LLM.
"""

import logging
import re
from typing import Literal

log = logging.getLogger(__name__)


# ── Token estimátor (bez externích závislostí) ────────────────────────────────

def _estimate_tokens(text: str) -> int:
    """
    Hrubý odhad počtu tokenů (cca 4 znaky = 1 token).
    Používáme bez tiktoken pro minimální závislosti.
    """
    return max(1, len(text) // 4)


# ── Sekce detektor ────────────────────────────────────────────────────────────

def _detect_sections(text: str) -> list[tuple[str | None, str]]:
    """
    Detekuje sekce v dokumentu podle H1/H2 nadpisů nebo prázdných řádků.

    Returns:
        list[(section_title, section_text)]
    """
    # Zkusíme najít markdown nadpisy (# nebo ##)
    h_pattern = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
    headers = list(h_pattern.finditer(text))

    if headers:
        # Dokument má nadpisy → dělíme podle nich
        sections = []
        for i, match in enumerate(headers):
            title = match.group(2).strip()
            start = match.end()
            end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
            body = text[start:end].strip()
            if body:
                sections.append((title, body))
        if sections:
            return sections

    # Fallback: dělení podle prázdných řádků (2+ řádků)
    paragraph_pattern = re.compile(r"\n{2,}")
    paragraphs = paragraph_pattern.split(text)
    return [(None, p.strip()) for p in paragraphs if p.strip()]


# DETERMINISTIC
def semantic_chunk(
    text: str,
    chunk_by: Literal["section_headers", "paragraphs"] = "section_headers",
    overlap_tokens: int = 200,
    max_chunk_tokens: int = 2000,
    source_id: str = "unknown",
) -> list[dict]:
    """
    Dělí dokument podle smyslu, NE po stránkách.

    Args:
        text:             Vstupní text dokumentu
        chunk_by:         Strategie dělení ("section_headers" | "paragraphs")
        overlap_tokens:   Počet tokenů přesahu mezi sousedními chunky (zabrání
                          ztrátě kontextu na hranicích sekcí)
        max_chunk_tokens: Maximální velikost jednoho chunku v tokenech
        source_id:        Identifikátor zdroje dokumentu (pro citace)

    Returns:
        list[dict] — každý chunk obsahuje:
            - text:             str — obsah chunku
            - section_title:    str | None — název sekce
            - chunk_index:      int — pořadové číslo
            - overlap_with_prev: str — konec předchozího chunku (overlap)
            - source_id:        str — identifikátor zdroje
            - token_estimate:   int — odhadovaný počet tokenů

    Příklad scénáře overlap:
        Sekce A (konec): "zástavní právo k nemovitosti X"
        Sekce B (začátek): "věcné břemeno na výše uvedené nemovitosti"

        Bez overlapu: agent čtoucí Sekci B neví o jakých nemovitostech je řeč.
        S overlapem: začátek Sekce B obsahuje konec Sekce A → kontext zachován.
    """
    log.info(
        f"[SemanticChunk] Zahajuji chunking | source_id={source_id} "
        f"strategy={chunk_by} overlap={overlap_tokens} max={max_chunk_tokens}"
    )

    if not text or not text.strip():
        log.warning(f"[SemanticChunk] Prázdný text pro source_id={source_id}")
        return []

    # Detekce sekcí podle strategie
    if chunk_by == "section_headers":
        raw_sections = _detect_sections(text)
    else:
        # paragraphs: dělení výhradně dle prázdných řádků
        para_pattern = re.compile(r"\n{2,}")
        paragraphs = para_pattern.split(text)
        raw_sections = [(None, p.strip()) for p in paragraphs if p.strip()]

    # Sloučení krátkých sekcí a rozdělení příliš velkých
    final_sections: list[tuple[str | None, str]] = []
    current_title: str | None = None
    current_text_parts: list[str] = []
    current_tokens: int = 0

    for title, body in raw_sections:
        body_tokens = _estimate_tokens(body)

        if current_tokens + body_tokens > max_chunk_tokens and current_text_parts:
            # Ulož aktuální chunk a začni nový
            final_sections.append((current_title, "\n\n".join(current_text_parts)))
            current_text_parts = []
            current_tokens = 0
            current_title = title

        # Pokud je samotné body větší než max, rozděl po větách
        if body_tokens > max_chunk_tokens:
            sentences = re.split(r"(?<=[.!?])\s+", body)
            temp_parts: list[str] = []
            temp_tokens = 0
            for sent in sentences:
                sent_tokens = _estimate_tokens(sent)
                if temp_tokens + sent_tokens > max_chunk_tokens and temp_parts:
                    final_sections.append((title, " ".join(temp_parts)))
                    temp_parts = []
                    temp_tokens = 0
                temp_parts.append(sent)
                temp_tokens += sent_tokens
            if temp_parts:
                final_sections.append((title, " ".join(temp_parts)))
        else:
            if not current_title and title:
                current_title = title
            current_text_parts.append(body)
            current_tokens += body_tokens

    if current_text_parts:
        final_sections.append((current_title, "\n\n".join(current_text_parts)))

    # Sestavení výstupních chunků s overlapem
    chunks: list[dict] = []
    all_texts = [t for _, t in final_sections]

    for i, (section_title, section_text) in enumerate(final_sections):
        # Overlap: konec předchozího chunku
        overlap_text = ""
        if i > 0 and overlap_tokens > 0:
            prev_text = all_texts[i - 1]
            # Vezmeme posledních ~overlap_tokens tokenů z předchozí sekce
            chars_for_overlap = overlap_tokens * 4  # cca 4 znaky = 1 token
            overlap_text = prev_text[-chars_for_overlap:].strip()

        chunk = {
            "text":             section_text,
            "section_title":    section_title,
            "chunk_index":      i,
            "overlap_with_prev": overlap_text,
            "source_id":        source_id,
            "token_estimate":   _estimate_tokens(section_text),
        }
        chunks.append(chunk)
        log.debug(
            f"[SemanticChunk] Chunk {i} | title={section_title!r} "
            f"tokens={chunk['token_estimate']} overlap_len={len(overlap_text)}"
        )

    log.info(
        f"[SemanticChunk] Hotovo | source_id={source_id} "
        f"chunks={len(chunks)} total_tokens≈{sum(c['token_estimate'] for c in chunks)}"
    )
    return chunks


def chunks_to_context(chunks: list[dict], include_titles: bool = True) -> str:
    """
    Spojí chunky do jednoho kontextového textu pro LLM prompt.
    Používá se při sestavení kontextu pro Maker agenta.
    """
    parts = []
    for chunk in chunks:
        if include_titles and chunk.get("section_title"):
            parts.append(f"### {chunk['section_title']}")
        if chunk.get("overlap_with_prev"):
            parts.append(f"[...předchozí kontext: {chunk['overlap_with_prev'][-200:]}...]")
        parts.append(chunk["text"])
    return "\n\n".join(parts)


if __name__ == "__main__":
    # Smoke test
    sample_doc = """
# Finanční výkazy FY2024

Společnost vykázala obrat 1.2 mld CZK za rok 2024.

## EBITDA a ziskovost

EBITDA dosáhla hodnoty 180 M CZK, což představuje EBITDA marži 15 %.

## Dluhové financování

Čistý dluh je 684 M CZK při zástavě nemovitosti v Praze 5.

## Závazky a pohledávky

Věcné břemeno na výše uvedené nemovitosti zajišťuje splácení úvěru.
Krátkodobé závazky dosáhly 420 M CZK.
"""

    chunks = semantic_chunk(sample_doc, source_id="cbs_2024")
    print(f"Chunků: {len(chunks)}")
    for c in chunks:
        print(f"  [{c['chunk_index']}] {c['section_title']!r} — {c['token_estimate']} tokenů")
        if c["overlap_with_prev"]:
            print(f"       overlap: {c['overlap_with_prev'][:80]}...")

    # Test overlap zachycuje "nemovitost v Praze 5" pro sekci o závazku
    assert len(chunks) >= 2
    # Poslední chunk by měl mít overlap z předchozí sekce
    assert chunks[-1]["overlap_with_prev"] != ""

    print("OK — chunking.py smoke test passed")
