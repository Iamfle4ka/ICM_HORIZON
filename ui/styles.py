"""
UI Styles & Constants — ui/styles.py
Vizuální manuál: Manrope font, accent #4D25EB, text #0B0F17.
"""

# ── Brand / Design-system barvy ───────────────────────────────────────────────

ACCENT       = "#4D25EB"   # primární akcent
ACCENT_DARK  = "#3A1BB8"   # hover stav akcentu
BG           = "#FFFFFF"
TEXT_MAIN    = "#0B0F17"
TEXT_SEC     = "#4B5563"
DIVIDER      = "#E5E7EB"
SURFACE      = "#F9FAFB"   # jemné plochy / karty

# Zachováváme Citi jméno pro existující reference
CITI_BLUE     = ACCENT
CITI_LIGHT    = ACCENT_DARK
CITI_GRAY     = TEXT_SEC
CITI_LIGHT_BG = SURFACE
CITI_WHITE    = BG

# Early Warning
EW_COLORS: dict[str, str] = {
    "GREEN": "#16A34A",
    "AMBER": "#D97706",
    "RED":   "#DC2626",
}

STATUS_COLORS: dict[str, str] = {
    "running":        "#3B82F6",
    "frozen":         "#6B7280",
    "escalated":      "#D97706",
    "awaiting_human": ACCENT,
    "completed":      "#16A34A",
    "failed":         "#DC2626",
}

STATUS_LABELS: dict[str, str] = {
    "running":        "Zpracovávám",
    "frozen":         "Zmraženo",
    "escalated":      "Eskalováno",
    "awaiting_human": "Čeká na review",
    "completed":      "Schváleno",
    "failed":         "Zamítnuto",
}


# ── CSS ────────────────────────────────────────────────────────────────────────

GLOBAL_CSS = """
<style>
    /* ── Manrope font ── */
    @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@300;400;600;700&display=swap');

    html, body, [class*="css"], .stApp, .stMarkdown, .stMetric,
    button, input, select, textarea {
        font-family: 'Manrope', sans-serif !important;
        color: #0B0F17;
    }

    /* ── Global background ── */
    .stApp { background-color: #FFFFFF; }
    section[data-testid="stSidebar"] { background-color: #F9FAFB; border-right: 1px solid #E5E7EB; }

    /* ── Page header ── */
    .icm-header {
        background: #4D25EB;
        color: white;
        padding: 1.1rem 1.5rem;
        border-radius: 10px;
        margin-bottom: 1.2rem;
    }
    .icm-header h2 { margin: 0; font-size: 1.3rem; font-weight: 700; letter-spacing: -0.3px; }
    .icm-header p  { margin: 0.2rem 0 0; font-size: 0.82rem; opacity: 0.85; }

    /* ── Metric cards ── */
    .metric-card {
        background: #FFFFFF;
        border: 1px solid #E5E7EB;
        border-radius: 8px;
        padding: 0.9rem 1.1rem;
        text-align: center;
    }
    .metric-card .label {
        font-size: 0.72rem;
        color: #4B5563;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 0.25rem;
    }
    .metric-card .value { font-size: 1.4rem; font-weight: 700; color: #0B0F17; }

    /* ── Streamlit metric override ── */
    [data-testid="metric-container"] label {
        font-size: 0.75rem !important;
        color: #4B5563 !important;
        font-weight: 600;
    }
    [data-testid="metric-container"] [data-testid="stMetricValue"] {
        font-size: 1.3rem !important;
        font-weight: 700 !important;
        color: #0B0F17 !important;
    }

    /* ── Buttons ── */
    .stButton > button[kind="primary"] {
        background: #4D25EB !important;
        border: none !important;
        color: white !important;
        font-weight: 600 !important;
        border-radius: 6px !important;
    }
    .stButton > button[kind="primary"]:hover {
        background: #3A1BB8 !important;
    }
    .stButton > button[kind="secondary"] {
        border: 1px solid #E5E7EB !important;
        color: #0B0F17 !important;
        font-weight: 500 !important;
        border-radius: 6px !important;
        background: #FFFFFF !important;
    }

    /* ── Sidebar nav buttons ── */
    section[data-testid="stSidebar"] .stButton > button {
        border-radius: 6px !important;
        font-weight: 500 !important;
    }
    section[data-testid="stSidebar"] .stButton > button[kind="primary"] {
        background: #4D25EB !important;
    }

    /* ── Dividers ── */
    hr { border: none; border-top: 1px solid #E5E7EB; margin: 1rem 0; }

    /* ── Status badge ── */
    .status-badge {
        display: inline-block;
        padding: 0.2rem 0.65rem;
        border-radius: 5px;
        font-size: 0.78rem;
        font-weight: 600;
        color: white;
    }

    /* ── EW badge ── */
    .ew-badge {
        display: inline-block;
        padding: 0.15rem 0.55rem;
        border-radius: 5px;
        font-size: 0.82rem;
        font-weight: 700;
        color: white;
    }

    /* ── Client row ── */
    .client-row {
        border: 1px solid #E5E7EB;
        border-radius: 8px;
        padding: 0.75rem 1rem;
        margin-bottom: 0.5rem;
        background: #FFFFFF;
    }
    .client-row:hover { border-color: #4D25EB; }

    /* ── Credit Memo container ── */
    .memo-container {
        background: #FFFFFF;
        border: 1px solid #E5E7EB;
        border-radius: 8px;
        padding: 1.5rem 2rem;
        line-height: 1.75;
        font-family: 'Manrope', sans-serif;
    }

    /* ── Citation highlight ── */
    .citation {
        background: #EDE9FC;
        color: #4D25EB;
        padding: 0 3px;
        border-radius: 3px;
        font-size: 0.8em;
        font-family: monospace;
    }

    /* ── Audit trail event ── */
    .audit-event {
        border-left: 3px solid #4D25EB;
        padding: 0.45rem 0.75rem;
        margin: 0.35rem 0;
        background: #F9FAFB;
        border-radius: 0 6px 6px 0;
        font-size: 0.84rem;
    }
    .audit-event.det { border-left-color: #9CA3AF; }
    .audit-event.ai  { border-left-color: #4D25EB; }

    /* ── Section title ── */
    .section-title {
        font-size: 1rem;
        font-weight: 700;
        color: #0B0F17;
        margin: 1.2rem 0 0.6rem;
        display: flex;
        align-items: center;
        gap: 0.4rem;
    }

    /* ── Expander ── */
    .streamlit-expanderHeader {
        font-weight: 600 !important;
        color: #0B0F17 !important;
    }

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab"] {
        font-weight: 600;
        color: #4B5563;
    }
    .stTabs [aria-selected="true"] {
        color: #4D25EB !important;
        border-bottom-color: #4D25EB !important;
    }

    /* ── Input fields ── */
    .stTextInput input, .stSelectbox select, .stTextArea textarea {
        border-radius: 6px !important;
        border: 1px solid #E5E7EB !important;
        font-family: 'Manrope', sans-serif !important;
    }
    .stTextInput input:focus, .stTextArea textarea:focus {
        border-color: #4D25EB !important;
        box-shadow: 0 0 0 2px rgba(77,37,235,0.12) !important;
    }

    /* ── Scrollable box ── */
    .scroll-box { max-height: 500px; overflow-y: auto; padding-right: 0.5rem; }

    /* ── WCR rows ── */
    .wcr-row-pass { background-color: #F0FDF4; }
    .wcr-row-fail { background-color: #FEF2F2; }

    /* ── Decision panel ── */
    .decision-panel {
        background: #F9FAFB;
        border: 1px solid #E5E7EB;
        border-radius: 8px;
        padding: 1.25rem 1.5rem;
        margin-top: 1rem;
    }

    /* ── Info / warning / success boxes ── */
    .stAlert { border-radius: 6px !important; font-family: 'Manrope', sans-serif !important; }
</style>
"""


# ── Helper funkce ──────────────────────────────────────────────────────────────

def page_header(icon: str, title: str, subtitle: str = "") -> str:
    """Vrátí HTML hlavičku stránky dle vizuálního manuálu."""
    sub = f"<p style='margin:0.2rem 0 0;font-size:0.82rem;opacity:0.85'>{subtitle}</p>" if subtitle else ""
    return (
        f"<div class='icm-header'>"
        f"<h2>{icon} {title}</h2>{sub}"
        f"</div>"
    )


def ew_badge_html(level: str) -> str:
    color = EW_COLORS.get(level, CITI_GRAY)
    icons = {"GREEN": "🟢", "AMBER": "🟡", "RED": "🔴"}
    icon  = icons.get(level, "⚪")
    return f'<span class="ew-badge" style="background:{color}">{icon} {level}</span>'


def status_badge_html(status: str) -> str:
    key   = status.replace("ProcessStatus.", "").lower()
    color = STATUS_COLORS.get(key, CITI_GRAY)
    label = STATUS_LABELS.get(key, key.upper())
    return f'<span class="status-badge" style="background:{color}">{label}</span>'


def wcr_icon(passed: bool) -> str:
    return "✅" if passed else "❌"


def fmt_czk(value: float | None, unit: str = "M CZK") -> str:
    if value is None:
        return "N/A"
    try:
        v = float(value)
        if unit == "M CZK":
            return f"{v / 1_000_000:,.1f} M CZK"
        return f"{v:,.0f} CZK"
    except (TypeError, ValueError):
        return str(value)


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.1f} %"
    except (TypeError, ValueError):
        return str(value)


def highlight_citations(memo_text: str) -> str:
    import re
    return re.sub(
        r"\[CITATION:([^\]]+)\]",
        r'<span class="citation">[CITATION:\1]</span>',
        memo_text,
    )


def node_type_badge(prompt_hash: str | None) -> str:
    return "🤖 AI" if prompt_hash else "⚙️ DET"
