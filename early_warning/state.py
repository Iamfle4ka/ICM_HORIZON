"""
Early Warning System State — early_warning/state.py
TypedDict definice pro EWS LangGraph pipeline.
DETERMINISTIC — žádný LLM.
"""
from __future__ import annotations

from enum import Enum
from typing import TypedDict


class AlertLevel(str, Enum):
    GREEN = "GREEN"
    AMBER = "AMBER"
    RED   = "RED"


class AlertType(str, Enum):
    UTILISATION_SPIKE  = "utilisation_spike"
    COVENANT_BREACH    = "covenant_breach"
    DPD_INCREASE       = "dpd_increase"
    REVENUE_DROP       = "revenue_drop"
    OVERDRAFT_RISK     = "overdraft_risk"
    TAX_RISK           = "tax_risk"


class EWAlert(TypedDict):
    ico:                str
    company_name:       str
    alert_type:         str
    alert_level:        str
    current_value:      float
    threshold:          float
    baseline:           float
    deviation_pct:      float
    description:        str
    recommended_action: str
    detected_at:        str


class EWState(TypedDict):
    run_id:           str
    run_type:         str        # "daily_batch" | "on_demand"
    triggered_at:     str
    portfolio:        list[dict]
    metrics_computed: dict       # ico → dict trendů
    alerts:           list       # list[EWAlert]
    summary:          dict
    status:           str
    audit_trail:      list
