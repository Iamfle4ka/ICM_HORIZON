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

from dotenv import load_dotenv
load_dotenv()  # загрузить .env ДО всех остальных импортов (data_connector читает ICM_ENV при импорте)

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
    page_title="GenAI pro underwriting — Horizon Bank",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── UI imports ─────────────────────────────────────────────────────────────────
from ui.styles import CITI_BLUE, GLOBAL_CSS
from ui.page_portfolio import render_portfolio_page
from ui.page_credit_memo import render_credit_memo_page
from ui.page_human_review import render_human_review_page
from ui.page_cases_log import render_cases_log_page
from ui.page_settings import render_settings_page
from ui.page_data_steward import render_data_steward_page

# ── Global CSS ─────────────────────────────────────────────────────────────────
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


# ── Sidebar navigace ───────────────────────────────────────────────────────────

def render_sidebar() -> str:
    """Renderuje sidebar navigaci a vrátí vybranou stránku."""
    with st.sidebar:
        import base64, pathlib
        _logo_path = pathlib.Path(__file__).parent / "static" / "horizon_logo.png"
        if _logo_path.exists():
            _logo_b64 = base64.b64encode(_logo_path.read_bytes()).decode()
            _logo_html = f'<img src="data:image/png;base64,{_logo_b64}" style="width:80%;max-width:160px;margin-bottom:0.4rem">'
        else:
            _logo_html = '<div style="font-size:1.8rem">🏦</div>'

        st.markdown(
            f"""
            <div style="background:{CITI_BLUE};color:white;padding:1rem;
                 border-radius:10px;margin-bottom:1rem;text-align:center">
                {_logo_html}
                <div style="font-weight:700;font-size:0.95rem;margin-top:0.3rem">GenAI pro underwriting</div>
                <div style="font-size:0.72rem;opacity:0.8">Horizon Bank</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("### Navigace")

        pages = {
            "portfolio":     "📊 Portfolio + EWS",
            "credit_memo":   "📄 Credit Memo",
            "human_review":  "👁️ Human Review",
            "cases_log":     "📋 Cases Log",
            "data_steward":  "🔬 Data Steward",
            "settings":      "⚙️ Nastavení",
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
            from utils.data_connector import get_client_info
            client = get_client_info(selected_ico)
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
            "GenAI pro underwriting v1.0<br>"
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
    elif page == "cases_log":
        render_cases_log_page()
    elif page == "data_steward":
        render_data_steward_page()
    elif page == "settings":
        render_settings_page()
    else:
        st.error(f"Neznámá stránka: {page}")


if __name__ == "__main__":
    main()
