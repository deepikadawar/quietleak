"""Synthetic data for 'Aarav'. Nothing here is real.

Deliberately includes traps a naive detector would get wrong:
  * food-delivery and grocery orders (repeat, but irregular)  -> must NOT be flagged
  * rent (regular, but a fixed obligation)                    -> not a subscription
  * electricity (regular dates, varying amount)               -> variable bill
  * an annual plan                                            -> missed by monthly-only logic
  * a stopped subscription whose mandate is still active      -> dormant mandate
  * an active mandate with no recognisable merchant           -> orphan mandate
"""
from __future__ import annotations

from datetime import date

from models import Mandate, Notification, Txn, Usage

TODAY = date(2026, 10, 31)          # fixed so the demo is reproducible

# alias fragments (squashed, upper-case) -> friendly service name
REFERENCE = {
    "MusicApp": ["MUSICAPP"],
    "VideoStream": ["VIDSTRM", "VIDEOSTREAM"],
    "CloudStore": ["CLDSTOR", "CLOUDSTORE"],
    "LearnApp": ["LEARNAPP"],
    "FitnessPlus": ["FITNESSPLUS"],
    "DailyNews": ["DAILYNEWS"],
    "FitZone": ["FITZONE"],
}

# how the user says each service is paid (used as the default in the cancellation helper)
PAYMENT_METHOD = {
    "MusicApp": "UPI AutoPay",
    "VideoStream": "UPI AutoPay",
    "LearnApp": "UPI AutoPay",
    "CloudStore": "Debit or credit card",
    "FitnessPlus": "App store billing",
    "DailyNews": "Debit or credit card",
    "FitZone": "UPI AutoPay",
}

# fictional cheaper plans for the "downgrade" option in the simulator
DOWNGRADE_PRICE = {
    "MusicApp": 99, "VideoStream": 149, "CloudStore": 99,
    "LearnApp": 199, "FitnessPlus": 600, "DailyNews": 799,
}

_MONTHS = [(2025, 10), (2025, 11), (2025, 12), (2026, 1), (2026, 2), (2026, 3),
           (2026, 4), (2026, 5), (2026, 6), (2026, 7), (2026, 8), (2026, 9), (2026, 10)]
_JITTER = [0, 0, 1, 0, -1, 0, 1, 0, 0, -1, 0, 1, 0]   # real debits drift by a day or two


def _monthly(raw, day, amounts, months=_MONTHS, jitter=True):
    out = []
    for i, ((y, m), amt) in enumerate(zip(months, amounts)):
        d = day + (_JITTER[i % len(_JITTER)] if jitter else 0)
        out.append(Txn(date(y, m, max(1, min(d, 28))), raw, amt))
    return out


def transactions() -> list:
    t = []
    t += _monthly("MUSICAPP*PREM", 5, [99] * 11 + [149] * 2)                 # price rise in Sep 2026
    t += _monthly("VIDSTRM INDIA", 12, [299] * 2, months=_MONTHS[-2:], jitter=False)  # started after a trial
    t += _monthly("CLDSTOR SUBS", 20, [199] * 13)
    t += _monthly("LEARNAPP PRO", 1, [499] * 13)                            # paid for, but unused since May
    t += [Txn(date(2025, 11, 15), "FITNESSPLUS", 1200), Txn(date(2026, 2, 15), "FITNESSPLUS", 1200),
          Txn(date(2026, 5, 15), "FITNESSPLUS", 1200), Txn(date(2026, 8, 15), "FITNESSPLUS", 1200)]
    t += [Txn(date(2025, 10, 18), "DAILYNEWS ANNUAL", 1499), Txn(date(2026, 10, 18), "DAILYNEWS ANNUAL", 1499)]
    t += _monthly("FITZONE GYM", 2, [799] * 6, months=_MONTHS[:6], jitter=False)   # stopped after March

    # ---- things that must NOT be flagged as subscriptions ----
    t += _monthly("RENT TRANSFER SHARMA", 1, [18000] * 13, jitter=False)
    t += _monthly("BSES ELECTRICITY BILL", 9,
                  [1420, 2110, 980, 860, 790, 1010, 1650, 2480, 2890, 2760, 2350, 1530, 1190])
    swiggy_gaps = [3, 11, 2, 19, 7, 5, 14, 1, 9]
    amounts = [312, 455, 189, 620, 280, 340, 515, 230, 410, 365]
    d = date(2026, 7, 6).toordinal()
    t.append(Txn(date.fromordinal(d), "SWIGGY*ORDER", amounts[0]))
    for gap, amt in zip(swiggy_gaps, amounts[1:]):
        d += gap
        t.append(Txn(date.fromordinal(d), "SWIGGY*ORDER", amt))
    bb = [date(2026, 8, 3), date(2026, 8, 9), date(2026, 8, 26), date(2026, 9, 4),
          date(2026, 9, 27), date(2026, 10, 1), date(2026, 10, 22)]
    t += [Txn(x, "BIGBASKET", a) for x, a in zip(bb, [1240, 860, 1510, 700, 1320, 940, 1180])]
    return sorted(t, key=lambda x: x.date)


def mandates() -> list:
    return [
        Mandate("M001", "MUSICAPP*PREM", 149, "monthly", "active", date(2025, 6, 10), date(2026, 10, 5)),
        Mandate("M002", "VIDSTRM INDIA", 299, "monthly", "active", date(2026, 8, 12), date(2026, 10, 12)),
        Mandate("M003", "LEARNAPP PRO", 499, "monthly", "active", date(2025, 3, 1), date(2026, 10, 1)),
        Mandate("M004", "XYZ DIGITAL SERVICES", 499, "monthly", "active", date(2026, 1, 14), None),   # orphan
        Mandate("M005", "FITZONE GYM", 799, "monthly", "active", date(2025, 4, 2), date(2026, 3, 2)),  # dormant
    ]


def notifications() -> list:
    return [
        Notification(date(2026, 8, 28), "MusicApp", "price_change",
                     "Premium plan price changes from ₹99 to ₹149 per month from 5 Sep."),
        Notification(date(2026, 9, 9), "VideoStream", "trial_ending",
                     "Your free trial ends on 12 Sep. You will be charged ₹299/month after that."),
        Notification(date(2026, 10, 17), "DailyNews", "pre_debit",
                     "Your annual plan renews on 18 Oct for ₹1,499."),
    ]


def usage() -> list:
    return [
        Usage("MusicApp", date(2026, 10, 29)), Usage("VideoStream", date(2026, 10, 25)),
        Usage("CloudStore", date(2026, 10, 28)), Usage("LearnApp", date(2026, 5, 20)),
        Usage("FitnessPlus", date(2026, 9, 20)), Usage("DailyNews", date(2026, 10, 30)),
        Usage("FitZone", date(2026, 2, 27)),
    ]
