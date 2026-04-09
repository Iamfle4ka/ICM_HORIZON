"""
UI Styles & Constants — ui/styles.py
Citi Bank design system: barvy, CSS, helper funkce.
"""

# ── Citi Brand Colors ──────────────────────────────────────────────────────────

CITI_BLUE     = "#003B70"
CITI_LIGHT    = "#0066CC"
CITI_RED      = "#C41230"
CITI_GOLD     = "#B8892A"
CITI_GRAY     = "#6B7280"
CITI_LIGHT_BG = "#F0F4F8"
CITI_WHITE    = "#FFFFFF"

# Early Warning barvy
EW_COLORS: dict[str, str] = {
    "GREEN": "#16A34A",
    "AMBER": "#D97706",
    "RED":   "#DC2626",
}

# Status badge barvy
STATUS_COLORS: dict[str, str] = {
    "running":        "#3B82F6",
    "frozen":         "#6B7280",
    "escalated":      "#F59E0B",
    "awaiting_human": "#8B5CF6",
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
    /* Citi Brand Header */
    .citi-header {
        background: linear-gradient(135deg, #003B70 0%, #0066CC 100%);
        color: white;
        padding: 1rem 2rem;
        border-radius: 0 0 12px 12px;
        margin-bottom: 1.5rem;
    }
    .citi-header h1 {
        margin: 0;
        font-size: 1.6rem;
        font-weight: 700;
        letter-spacing: -0.5px;
    }
    .citi-header p {
        margin: 0.2rem 0 0;
        font-size: 0.85rem;
        opacity: 0.85;
    }

    /* Metric cards */
    .metric-card {
        background: white;
        border: 1px solid #E5E7EB;
        border-radius: 10px;
        padding: 1rem 1.2rem;
        box-shadow: 0 1px 4px rgba(0,0,0,0.06);
        text-align: center;
    }
    .metric-card .label {
        font-size: 0.75rem;
        color: #6B7280;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 0.3rem;
    }
    .metric-card .value {
        font-size: 1.5rem;
        font-weight: 700;
        color: #111827;
    }
    .metric-card .status {
        font-size: 0.8rem;
        margin-top: 0.2rem;
    }

    /* Status badge */
    .status-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-size: 0.8rem;
        font-weight: 600;
        color: white;
    }

    /* EW alert */
    .ew-badge {
        display: inline-block;
        padding: 0.2rem 0.6rem;
        border-radius: 6px;
        font-size: 0.85rem;
        font-weight: 700;
        color: white;
    }

    /* WCR table */
    .wcr-row-pass { background-color: #F0FDF4; }
    .wcr-row-fail { background-color: #FEF2F2; }

    /* Audit trail */
    .audit-event {
        border-left: 3px solid #0066CC;
        padding: 0.5rem 0.8rem;
        margin: 0.4rem 0;
        background: #F8FAFC;
        border-radius: 0 6px 6px 0;
        font-size: 0.85rem;
    }
    .audit-event.det {
        border-left-color: #6B7280;
    }
    .audit-event.ai {
        border-left-color: #0066CC;
    }

    /* Credit memo */
    .memo-container {
        background: white;
        border: 1px solid #E5E7EB;
        border-radius: 10px;
        padding: 1.5rem 2rem;
        font-family: 'Georgia', serif;
        line-height: 1.7;
    }

    /* Citation highlight */
    .citation {
        background: #EFF6FF;
        color: #1D4ED8;
        padding: 0 3px;
        border-radius: 3px;
        font-size: 0.8em;
        font-family: monospace;
    }

    /* Decision buttons */
    .decision-panel {
        background: #F8FAFC;
        border: 1px solid #E5E7EB;
        border-radius: 10px;
        padding: 1.5rem;
        margin-top: 1rem;
    }

    /* Scrollable containers */
    .scroll-box {
        max-height: 500px;
        overflow-y: auto;
        padding-right: 0.5rem;
    }

    /* Section divider */
    .section-divider {
        border: none;
        border-top: 2px solid #E5E7EB;
        margin: 1.5rem 0;
    }
</style>
"""


# ── Helper funkce ──────────────────────────────────────────────────────────────

def ew_badge_html(level: str) -> str:
    """Vrátí HTML badge pro Early Warning úroveň."""
    color = EW_COLORS.get(level, CITI_GRAY)
    icons = {"GREEN": "🟢", "AMBER": "🟡", "RED": "🔴"}
    icon = icons.get(level, "⚪")
    return (
        f'<span class="ew-badge" style="background:{color}">'
        f'{icon} {level}</span>'
    )


def status_badge_html(status: str) -> str:
    """Vrátí HTML badge pro ProcessStatus."""
    # Normalizace — odstraň enum prefix
    key = status.replace("ProcessStatus.", "").lower()
    color = STATUS_COLORS.get(key, CITI_GRAY)
    label = STATUS_LABELS.get(key, key.upper())
    return f'<span class="status-badge" style="background:{color}">{label}</span>'


def wcr_icon(passed: bool) -> str:
    return "✅" if passed else "❌"


def fmt_czk(value: float | None, unit: str = "M CZK") -> str:
    """Formátuje hodnotu v CZK."""
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
    """Formátuje hodnotu jako procento."""
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.1f} %"
    except (TypeError, ValueError):
        return str(value)


def highlight_citations(memo_text: str) -> str:
    """
    Zvýrazní [CITATION:source_id] tagy v textu pro HTML zobrazení.
    Použití: v UI page_credit_memo.py pro vizuální audit citací.
    """
    import re
    return re.sub(
        r"\[CITATION:([^\]]+)\]",
        r'<span class="citation">[CITATION:\1]</span>',
        memo_text,
    )


def node_type_badge(prompt_hash: str | None) -> str:
    """Vrátí badge AI nebo DET podle přítomnosti prompt_hash."""
    if prompt_hash:
        return "🤖 AI"
    return "⚙️ DET"
