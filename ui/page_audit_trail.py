"""
Audit Trail Viewer — ui/page_audit_trail.py
Immutable audit log každého pipeline run s rozlišením AI/DET uzlů.
"""

import streamlit as st

from ui.styles import CITI_BLUE, node_type_badge
from utils.audit import format_audit_trail_summary
from utils.mock_data import get_mock_agent_result
from utils.data_connector import get_portfolio_clients as get_portfolio


def render_audit_trail_page() -> None:
    """Renderuje Audit Trail stránku."""

    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,{CITI_BLUE} 0%,#0066CC 100%);
             color:white;padding:1.2rem 1.5rem;border-radius:10px;margin-bottom:1rem">
            <h2 style="margin:0;font-size:1.4rem">🔍 Audit Trail</h2>
            <p style="margin:0.2rem 0 0;font-size:0.85rem;opacity:0.85">
                Immutable log každé akce pipeline · AI uzly s prompt hash · DET uzly bez LLM
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Výběr klienta
    portfolio = get_portfolio()
    ico_options = [f"{c['ico']} — {c['company_name']}" for c in portfolio]
    ico_map = {f"{c['ico']} — {c['company_name']}": c["ico"] for c in portfolio}

    preselected = st.session_state.get("audit_ico") or st.session_state.get("selected_ico", "")
    default_idx = 0
    if preselected:
        matching = [i for i, opt in enumerate(ico_options) if opt.startswith(preselected)]
        if matching:
            default_idx = matching[0]

    selected_label = st.selectbox(
        "Vyberte klienta",
        options=ico_options,
        index=default_idx,
        key="audit_ico_select",
    )
    ico = ico_map[selected_label]

    # Načtení výsledku
    result_key = f"pipeline_result_{ico}"
    result = st.session_state.get(result_key)

    if result is None:
        if st.button("📥 Načíst demo audit trail", key="load_audit_demo"):
            result = get_mock_agent_result(ico)
            st.session_state[result_key] = result
            st.rerun()
        else:
            st.info("Spusťte pipeline na stránce 'Credit Memo' nebo načtěte demo audit trail.")
            return

    audit_trail = result.get("audit_trail", [])
    if not audit_trail:
        st.warning("Audit trail je prázdný.")
        return

    _render_audit_trail(audit_trail, result, ico)


def _render_audit_trail(audit_trail: list, result: dict, ico: str) -> None:
    """Renderuje audit trail s metadaty a export funkcí."""

    # Souhrnné statistiky
    ai_events = [e for e in audit_trail if e.get("prompt_hash")]
    det_events = [e for e in audit_trail if not e.get("prompt_hash")]
    total_tokens = sum(e.get("tokens_used") or 0 for e in audit_trail)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Celkem eventů", len(audit_trail))
    col2.metric("🤖 AI uzly", len(ai_events))
    col3.metric("⚙️ DET uzly", len(det_events))
    col4.metric("Celkem tokenů", f"{total_tokens:,}")

    # Filtr
    filter_type = st.radio(
        "Filtr uzlů",
        options=["Vše", "🤖 AI uzly", "⚙️ DET uzly"],
        horizontal=True,
        key="audit_filter",
    )

    filtered_events = audit_trail
    if filter_type == "🤖 AI uzly":
        filtered_events = ai_events
    elif filter_type == "⚙️ DET uzly":
        filtered_events = det_events

    st.markdown(f"**{len(filtered_events)} eventů** ({filter_type})")
    st.markdown("---")

    # Události
    for i, event in enumerate(filtered_events, 1):
        _render_audit_event(i, event)

    st.markdown("---")

    # Export
    with st.expander("📤 Export Audit Trail"):
        summary_text = format_audit_trail_summary(audit_trail)
        st.code(summary_text, language="text")
        st.download_button(
            "⬇️ Stáhnout audit trail (.txt)",
            data=summary_text,
            file_name=f"audit_trail_{ico}.txt",
            mime="text/plain",
        )

        # JSON export
        import json
        json_str = json.dumps(audit_trail, ensure_ascii=False, indent=2)
        st.download_button(
            "⬇️ Stáhnout audit trail (.json)",
            data=json_str,
            file_name=f"audit_trail_{ico}.json",
            mime="application/json",
        )


def _render_audit_event(index: int, event: dict) -> None:
    """Renderuje jeden audit event."""
    node = event.get("node", "N/A")
    action = event.get("action", "N/A")
    result = event.get("result", "N/A")
    timestamp = event.get("timestamp", "N/A")
    prompt_hash = event.get("prompt_hash")
    prompt_version = event.get("prompt_version")
    tokens = event.get("tokens_used")
    metadata = event.get("metadata", {})

    is_ai = bool(prompt_hash)
    border_color = "#0066CC" if is_ai else "#9CA3AF"
    bg_color = "#EFF6FF" if is_ai else "#F9FAFB"
    node_badge = node_type_badge(prompt_hash)

    # Výsledek badge
    result_color = "#16A34A"
    if any(kw in str(result).lower() for kw in ["fail", "freeze", "error", "breach", "low_"]):
        result_color = "#DC2626"
    elif any(kw in str(result).lower() for kw in ["pass", "success", "ok", "completed"]):
        result_color = "#16A34A"
    else:
        result_color = "#D97706"

    # Sestavení detail textu
    details = []
    if prompt_hash:
        details.append(f"hash:`{prompt_hash}`")
    if prompt_version:
        details.append(f"v{prompt_version}")
    if tokens:
        details.append(f"{tokens:,} tokenů")
    if metadata:
        meta_str = " · ".join(
            f"{k}={v}" for k, v in metadata.items()
            if k not in ("ico",) and v is not None and v != [] and v != {}
        )
        if meta_str:
            details.append(meta_str)

    detail_str = " · ".join(details) if details else ""

    st.markdown(
        f"""
        <div style="border-left:4px solid {border_color};background:{bg_color};
             padding:0.6rem 0.9rem;margin:0.4rem 0;border-radius:0 8px 8px 0">
            <div style="display:flex;justify-content:space-between;align-items:baseline">
                <span><strong>{index:02d}. {node}</strong>
                    <span style="margin-left:0.4rem;font-size:0.8rem;color:#6B7280">{node_badge}</span>
                </span>
                <span style="font-size:0.78rem;color:#9CA3AF">{timestamp[:19] if timestamp else ''}</span>
            </div>
            <div style="margin-top:0.2rem">
                <code style="background:#E5E7EB;padding:0.1rem 0.3rem;border-radius:3px;font-size:0.82rem">{action}</code>
                → <span style="color:{result_color};font-weight:600;font-size:0.85rem">{result}</span>
            </div>
            {f'<div style="font-size:0.78rem;color:#6B7280;margin-top:0.2rem">{detail_str}</div>' if detail_str else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )
