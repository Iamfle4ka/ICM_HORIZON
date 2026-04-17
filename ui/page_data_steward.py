"""
Data Steward — ui/page_data_steward.py
Quarantine Zone review: Data Steward může schválit nebo odmítnout záznamy
které selhaly DQ validací v Bronze Layer.
"""

import streamlit as st

from ui.styles import CITI_BLUE


def render_data_steward_page() -> None:
    """Renderuje Data Steward Quarantine Review stránku."""

    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,{CITI_BLUE} 0%,#1D4ED8 100%);
             color:white;padding:1.2rem 1.5rem;border-radius:10px;margin-bottom:1rem">
            <h2 style="margin:0;font-size:1.4rem">🔬 Data Steward — Quarantine Review</h2>
            <p style="margin:0.2rem 0 0;font-size:0.85rem;opacity:0.85">
                Bronze Layer · Záznamy čekající na DQ review
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    from bronze.quarantine import (
        get_quarantine,
        get_quarantine_summary,
        release_record,
        reject_record,
    )

    # ── Statistiky ─────────────────────────────────────────────────────────────
    summary = get_quarantine_summary()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Celkem", summary["total"])
    col2.metric("Čeká na review", summary["pending"], delta=None)
    col3.metric("Uvolněno", summary["released"])
    col4.metric("Odmítnuto", summary["rejected"])

    st.markdown("---")

    # ── Filtry ─────────────────────────────────────────────────────────────────
    col_f1, col_f2 = st.columns([2, 3])
    with col_f1:
        status_filter = st.selectbox(
            "Filtr statusu",
            options=["pending", "released", "rejected", "all"],
            index=0,
            key="qz_status_filter",
        )
    with col_f2:
        source_filter = st.text_input(
            "Filtr zdroje (prázdné = vše)",
            value="",
            placeholder="cribis | silver | justice | ares | ews | esg",
            key="qz_source_filter",
        )

    filter_val = None if status_filter == "all" else status_filter
    records = get_quarantine(status_filter=filter_val)

    if source_filter.strip():
        records = [r for r in records if r.get("source", "").lower() == source_filter.strip().lower()]

    if not records:
        st.info("Žádné záznamy v karanténě odpovídající filtru.")
    else:
        st.markdown(f"**Nalezeno {len(records)} záznam(ů)**")
        st.markdown("---")

    # ── Seznam záznamů ─────────────────────────────────────────────────────────
    for rec in records:
        record_id  = rec.get("record_id", "")
        status     = rec.get("status", "pending")
        source     = rec.get("source", "unknown")
        reason     = rec.get("reason", "")
        errors     = rec.get("errors", [])
        auto_fixed = rec.get("auto_fixed", [])
        q_at       = rec.get("quarantined_at", "")[:19].replace("T", " ")
        raw_record = rec.get("record", {})

        # Barva podle statusu
        status_colors = {
            "pending":  ("#FEF3C7", "#D97706", "⏳"),
            "released": ("#F0FDF4", "#16A34A", "✅"),
            "rejected": ("#FEF2F2", "#DC2626", "❌"),
        }
        bg, border_c, icon = status_colors.get(status, ("#F9FAFB", "#6B7280", "❓"))

        with st.expander(
            f"{icon} [{record_id}] {source} · {reason[:60]} · {q_at}",
            expanded=(status == "pending"),
        ):
            col_meta, col_rec = st.columns([2, 3])

            with col_meta:
                st.markdown(
                    f"""
                    <div style="background:{bg};border-left:4px solid {border_c};
                         padding:0.8rem;border-radius:6px">
                        <strong>Record ID:</strong> <code>{record_id}</code><br>
                        <strong>Zdroj:</strong> {source}<br>
                        <strong>Status:</strong> {status.upper()}<br>
                        <strong>Karanténa od:</strong> {q_at}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                if errors:
                    st.markdown("**Chyby DQ validace:**")
                    for e in errors:
                        st.markdown(f"- 🔴 {e}")

                if auto_fixed:
                    st.markdown("**Auto-opraveno před karanténou:**")
                    for f in auto_fixed:
                        st.markdown(f"- 🔧 {f}")

                reviewed_by = rec.get("reviewed_by")
                if reviewed_by:
                    st.markdown(
                        f"**Reviewer:** {reviewed_by}  \n"
                        f"**Čas review:** {rec.get('reviewed_at', '')[:19]}  \n"
                        f"**Poznámka:** {rec.get('review_note', '') or '—'}"
                    )

            with col_rec:
                st.markdown("**Raw záznam:**")
                if raw_record:
                    import json
                    st.code(json.dumps(raw_record, ensure_ascii=False, indent=2), language="json")
                else:
                    st.info("Raw data nejsou dostupná (prod mode).")

            # Akce — pouze pro pending záznamy
            if status == "pending":
                st.markdown("---")
                col_note, col_btns = st.columns([3, 2])

                with col_note:
                    note = st.text_input(
                        "Poznámka reviewera",
                        key=f"note_{record_id}",
                        placeholder="Důvod schválení / odmítnutí...",
                    )

                with col_btns:
                    st.markdown("<br>", unsafe_allow_html=True)
                    col_rel, col_rej = st.columns(2)

                    with col_rel:
                        if st.button(
                            "✅ Uvolnit",
                            key=f"release_{record_id}",
                            type="primary",
                            use_container_width=True,
                        ):
                            reviewer = st.session_state.get("reviewer_name", "data_steward")
                            ok = release_record(record_id, reviewed_by=reviewer, note=note)
                            if ok:
                                st.success(f"Záznam {record_id} uvolněn do Silver.")
                                st.rerun()
                            else:
                                st.error("Uvolnění selhalo.")

                    with col_rej:
                        if st.button(
                            "❌ Odmítnout",
                            key=f"reject_{record_id}",
                            use_container_width=True,
                        ):
                            reviewer = st.session_state.get("reviewer_name", "data_steward")
                            ok = reject_record(record_id, reviewed_by=reviewer, reason=note)
                            if ok:
                                st.warning(f"Záznam {record_id} odmítnut.")
                                st.rerun()
                            else:
                                st.error("Odmítnutí selhalo.")

    # ── Identita reviewera ─────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("---")
        st.markdown("**Data Steward**")
        reviewer_name = st.text_input(
            "Vaše jméno / login",
            value=st.session_state.get("reviewer_name", "data_steward"),
            key="reviewer_name_input",
        )
        if reviewer_name:
            st.session_state["reviewer_name"] = reviewer_name
