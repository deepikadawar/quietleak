"""Plain data containers for QuietLeak. No third-party dependencies."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


def inr(amount: float) -> str:
    """Format a whole-rupee amount, e.g. 1788 -> '₹1,788'."""
    return f"₹{int(round(amount)):,}"


# ---------- input records (all synthetic) ----------
@dataclass(frozen=True)
class Txn:
    date: date
    raw: str          # description exactly as it appears on the statement
    amount: int       # whole rupees


@dataclass(frozen=True)
class Mandate:
    mandate_id: str
    raw_merchant: str
    amount: int
    frequency: str            # weekly | monthly | quarterly | annual
    status: str               # active | revoked
    created: date
    last_debit: Optional[date]
    method: str = "UPI AutoPay"


@dataclass(frozen=True)
class Notification:
    date: date
    service: str
    kind: str                 # trial_ending | price_change | pre_debit
    text: str


@dataclass(frozen=True)
class Usage:
    service: str
    last_active: date


# ---------- output records ----------
@dataclass
class Evidence:
    label: str
    detail: str
    status: str               # ok | warn | info
    points: float = 0.0
    max_points: float = 0.0


@dataclass
class Series:
    key: str
    service: Optional[str]
    display_name: str
    raw_descriptions: list
    txns: list
    category: str                     # subscription | fixed_obligation | variable_bill | not_recurring
    reason: str = ""                  # why it was NOT treated as a subscription
    cadence: Optional[str] = None
    per_year: int = 0
    status: str = "active"            # active | stopped
    current_amount: int = 0
    annual_cost_estimate: int = 0     # ESTIMATE: current price x charges per year
    spent_last_12m: int = 0           # ACTUAL: sum of observed charges
    next_renewal: Optional[date] = None
    confidence_score: float = 0.0
    confidence_label: str = ""
    evidence: list = field(default_factory=list)
    price_change: Optional[dict] = None
    trial: Optional[dict] = None
    unused: Optional[dict] = None
    mandate: Optional[Mandate] = None
    id_how: str = ""                  # how the merchant was matched
    regularity: float = 0.0           # share of gaps that fit the cadence
    gaps: list = field(default_factory=list)
    pattern: str = ""                 # constant | step | variable


@dataclass
class MandateFinding:
    mandate: Mandate
    kind: str                         # orphan | dormant | linked
    service: Optional[str]
    headline: str
    evidence: list
    missing: list
    checklist: list
    annual_exposure: int


@dataclass
class Alert:
    priority: int                     # 1 = most urgent
    kind: str                         # orphan_mandate | dormant_mandate | trial_conversion | price_increase | unused
    title: str
    detail: str
    annual_impact: int
    target: str                       # service name or mandate id
