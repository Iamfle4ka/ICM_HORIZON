"""
ICM GenAI Platform — app.py
Hlavní Streamlit aplikace · Tým 7 · Citi Bank

Stránky:
  1. Portfolio Dashboard  — přehled 6 klientů, EW status
  2. Credit Memo          — spuštění AI pipeline, WCR, Checker
  3. Human Review         — 4-Eyes Rule, rozhodnutí underwritera
  4. Audit Trail          — immutable log, AI vs. DET uzly

Spuštění:
    streamlit run app.py
"""

import logging
import sys

import streamlit as st

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ── Streamlit konfigurace ──────────────────────────────────────────────────────
st.set_page_config(
    page_title="ICM GenAI Platform — Citi Bank",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── UI imports ─────────────────────────────────────────────────────────────────
from ui.styles import CITI_BLUE, GLOBAL_CSS
from ui.page_portfolio import render_portfolio_page
from ui.page_credit_memo import render_credit_memo_page
from ui.page_human_review import render_human_review_page
from ui.page_audit_trail import render_audit_trail_page

# ── Global CSS ─────────────────────────────────────────────────────────────────
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


# ── Sidebar navigace ───────────────────────────────────────────────────────────

def render_sidebar() -> str:
    """Renderuje sidebar navigaci a vrátí vybranou stránku."""
    with st.sidebar:
        st.markdown(
            f"""
            <div style="background:{CITI_BLUE};color:white;padding:1rem;
                 border-radius:10px;margin-bottom:1rem;text-align:center">
                <div style="font-size:1.8rem">🏦</div>
                <div style="font-weight:700;font-size:1.1rem">ICM GenAI</div>
                <div style="font-size:0.75rem;opacity:0.8">Citi Bank · Tým 7</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("### Navigace")

        pages = {
            "portfolio":    "📊 Portfolio Dashboard",
            "credit_memo":  "📄 Credit Memo",
            "human_review": "👁️ Human Review",
            "audit_trail":  "🔍 Audit Trail",
        }

        # Výchozí stránka
        if "page" not in st.session_state:
            st.session_state["page"] = "portfolio"

        for key, label in pages.items():
            active = st.session_state.get("page") == key
            btn_type = "primary" if active else "secondary"
            if st.button(label, key=f"nav_{key}", type=btn_type, use_container_width=True):
                st.session_state["page"] = key
                st.rerun()

        st.markdown("---")

        # Aktuální IČO info
        selected_ico = st.session_state.get("selected_ico", "")
        if selected_ico:
            from utils.mock_data import get_client
            client = get_client(selected_ico)
            if client:
                ew = client.get("ew_alert_level", "GREEN")
                ew_icons = {"GREEN": "🟢", "AMBER": "🟡", "RED": "🔴"}
                st.markdown(
                    f"**Aktivní klient:**  \n"
                    f"`{selected_ico}`  \n"
                    f"{client['company_name'][:25]}  \n"
                    f"{ew_icons.get(ew,'')} {ew}"
                )
                st.markdown("---")

        # Systémové info
        st.markdown(
            "<div style='font-size:0.75rem;color:#9CA3AF'>"
            "ICM GenAI Platform v1.0<br>"
            "LangGraph + Claude API<br>"
            "4-Eyes Rule enforced<br>"
            "Audit Trail: immutable"
            "</div>",
            unsafe_allow_html=True,
        )

    return st.session_state.get("page", "portfolio")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    """Hlavní funkce aplikace."""
    page = render_sidebar()

    log.debug(f"[App] Renderuji stránku: {page}")

    if page == "portfolio":
        render_portfolio_page()
    elif page == "credit_memo":
        render_credit_memo_page()
    elif page == "human_review":
        render_human_review_page()
    elif page == "audit_trail":
        render_audit_trail_page()
    else:
        st.error(f"Neznámá stránka: {page}")


if __name__ == "__main__":
    main()
