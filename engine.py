"""Detection and calculation logic. Standard library only, so it is easy to test."""
from __future__ import annotations

import re
import statistics
from collections import defaultdict
from datetime import date, timedelta
from difflib import SequenceMatcher

from models import Alert, Evidence, MandateFinding, Series, inr

# name: (typical gap in days, tolerance in days, charges per year)
CADENCES = {
    "weekly": (7, 1, 52),
    "monthly": (30, 4, 12),
    "quarterly": (91, 7, 4),
    "annual": (365, 10, 1),
}
PERIOD_WORD = {"weekly": "week", "monthly": "month", "quarterly": "quarter", "annual": "year"}
MIN_REGULARITY = 0.6          # share of gaps that must fit the cadence
UNUSED_AFTER_DAYS = 60
FIXED_OBLIGATION_WORDS = {"RENT", "EMI", "LOAN", "MORTGAGE"}


# ------------------------------------------------------------------ merchants
def normalize(raw: str) -> str:
    s = re.sub(r"[^A-Z0-9]+", " ", raw.upper())
    s = re.sub(r"\b\d{4,}\b", " ", s)                 # drop reference numbers
    return re.sub(r"\s+", " ", s).strip()


def identify_service(raw: str, reference: dict):
    """Return (service or None, score 0-1, how it matched)."""
    norm = normalize(raw)
    squashed = norm.replace(" ", "")
    for service, aliases in reference.items():
        for alias in aliases:
            if alias in squashed:
                return service, 1.0, f"alias '{alias}'"
    best = (None, 0.0, "no match in reference list")
    for service, aliases in reference.items():
        for token in norm.split():
            for alias in aliases:
                r = SequenceMatcher(None, token, alias).ratio()
                if r >= 0.85 and r > best[1]:
                    best = (service, round(r, 2), f"fuzzy '{token}' ~ '{alias}'")
    return best


# ------------------------------------------------------------------ dates
def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y += d.year
    m += 1
    day = min(d.day, [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return date(y, m, day)


def advance(d: date, cadence: str) -> date:
    return {"weekly": d + timedelta(days=7), "monthly": add_months(d, 1),
            "quarterly": add_months(d, 3), "annual": add_months(d, 12)}[cadence]


def detect_cadence(gaps):
    med = statistics.median(gaps)
    best = min(CADENCES, key=lambda c: abs(CADENCES[c][0] - med))
    days, tol, _ = CADENCES[best]
    if abs(med - days) > tol + 3:
        return None, 0.0
    fit = sum(1 for g in gaps if abs(g - days) <= tol) / len(gaps)
    return best, fit


# ------------------------------------------------------------------ recurring payments
def analyse(transactions, reference, notifications, usage, mandates, today) -> list:
    groups, meta = defaultdict(list), {}
    for t in sorted(transactions, key=lambda x: x.date):
        svc, score, how = identify_service(t.raw, reference)
        key = svc or normalize(t.raw)
        groups[key].append(t)
        meta.setdefault(key, (svc, score, how))
    series = [_analyse_group(k, meta[k], txns, notifications, usage, today) for k, txns in groups.items()]

    for m in mandates:                                # attach active mandates to matching series
        if m.status != "active":
            continue
        svc, _, _ = identify_service(m.raw_merchant, reference)
        for s in series:
            if s.category == "subscription" and ((svc and s.service == svc) or _same_merchant(m.raw_merchant, s)):
                s.mandate = m
    for s in series:
        if s.category == "subscription":
            _finalise_confidence(s, notifications)
    return sorted(series, key=lambda s: (s.category != "subscription", -s.annual_cost_estimate))


def _same_merchant(raw: str, s: Series) -> bool:
    a = normalize(raw)
    return any(SequenceMatcher(None, a, normalize(r)).ratio() >= 0.85 for r in s.raw_descriptions)


def _analyse_group(key, meta, txns, notifications, usage, today) -> Series:
    service, id_score, id_how = meta
    raws = sorted({t.raw for t in txns})
    s = Series(key=key, service=service, display_name=service or txns[-1].raw,
               raw_descriptions=raws, txns=txns, category="not_recurring")
    s.id_how = id_how
    amounts = [t.amount for t in txns]
    s.current_amount = amounts[-1]
    s.spent_last_12m = sum(t.amount for t in txns if (today - t.date).days < 365)

    if len(txns) < 2:
        s.reason = "Only one charge seen, so no pattern can be established."
        return s

    gaps = [(b.date - a.date).days for a, b in zip(txns, txns[1:])]
    cadence, fit = detect_cadence(gaps)
    if cadence is None or fit < MIN_REGULARITY:
        s.reason = (f"{len(txns)} payments, but the gaps range from {min(gaps)} to {max(gaps)} days"
                    + (f" and only {round(fit * len(gaps))} of {len(gaps)} fit a {cadence} pattern." if cadence else
                       " with no regular rhythm.")
                    + " Repeat purchases are not the same as a subscription.")
        return s

    days, tol, per_year = CADENCES[cadence]
    s.cadence, s.per_year, s.regularity, s.gaps = cadence, per_year, fit, gaps
    changes = sum(1 for a, b in zip(amounts, amounts[1:]) if a != b)
    spread = max(amounts) / min(amounts)
    pattern, step_idx = "constant", None
    if changes:
        step_idx = max(i for i in range(1, len(amounts)) if amounts[i] != amounts[i - 1])
        single_step = all(a == amounts[step_idx] for a in amounts[step_idx:]) and \
            all(a == amounts[0] for a in amounts[:step_idx])
        pattern = "variable" if (spread >= 1.15 and changes >= 3) or not single_step else "step"
    s.pattern = pattern

    tokens = set(normalize(" ".join(raws)).split())
    if tokens & FIXED_OBLIGATION_WORDS:
        s.category = "fixed_obligation"
        s.reason = f"Regular {cadence} payment of a fixed amount, but the description looks like rent, a loan or an EMI. Treated as a fixed obligation, not a subscription."
        return s
    if pattern == "variable":
        s.category = "variable_bill"
        s.reason = (f"Regular {cadence} dates, but the amount swings between {inr(min(amounts))} and {inr(max(amounts))}. "
                    "That looks like a usage-based bill, not a subscription.")
        return s

    s.category = "subscription"
    s.status = "active" if (today - txns[-1].date).days <= days * 1.5 + tol else "stopped"
    s.annual_cost_estimate = s.current_amount * per_year if s.status == "active" else 0
    s.next_renewal = advance(txns[-1].date, cadence) if s.status == "active" else None

    if pattern == "step":
        prev, new = amounts[step_idx - 1], amounts[step_idx]
        notice = next((n for n in notifications if n.service == service and n.kind == "price_change"
                       and n.date <= txns[step_idx].date), None)
        s.price_change = dict(previous=prev, new=new, diff=new - prev, since=txns[step_idx].date,
                              annual_impact=(new - prev) * per_year, notice=notice)

    if service:
        first = txns[0].date
        for n in notifications:
            if n.service == service and n.kind == "trial_ending" and 0 <= (first - n.date).days <= 21:
                s.trial = dict(notice=n, first_charge=first, amount=txns[0].amount)
        for u in usage:
            if u.service == service and s.status == "active":
                idle = (today - u.last_active).days
                if idle >= UNUSED_AFTER_DAYS:
                    s.unused = dict(last_active=u.last_active, idle_days=idle)
    return s


def _finalise_confidence(s: Series, notifications) -> None:
    ev, n = [], len(s.txns)
    gmin, gmax = min(s.gaps), max(s.gaps)
    fits = round(s.regularity * len(s.gaps))
    ev.append(Evidence("Repeated payments found",
                       f"{n} charges with a {s.cadence} rhythm (gaps {gmin}-{gmax} days; {fits} of {len(s.gaps)} fit).",
                       "ok" if s.regularity >= 0.8 else "warn", 40 * s.regularity, 40))
    amounts = [t.amount for t in s.txns]
    if s.pattern == "constant":
        ev.append(Evidence("Amount is consistent", f"Every charge is {inr(amounts[0])}.", "ok", 25, 25))
    else:
        pc = s.price_change
        ev.append(Evidence("Amount changed once",
                           f"{inr(pc['previous'])} until the change, {inr(pc['new'])} since {pc['since']:%d %b %Y}.",
                           "ok", 20, 25))
    if s.service:
        ev.append(Evidence("Service recognised", f"Matched to {s.service} ({s.id_how}).", "ok", 20, 20))
    else:
        ev.append(Evidence("Service not confirmed", "The merchant description doesn't identify the exact service.",
                           "warn", 0, 20))
    support = [x.text for x in notifications if s.service and x.service == s.service]
    if s.mandate:
        support.append(f"Active {s.mandate.method} mandate {s.mandate.mandate_id} for {inr(s.mandate.amount)}/{s.mandate.frequency}.")
    if support:
        ev.append(Evidence("Supporting records", " | ".join(support), "ok", 15, 15))
    else:
        ev.append(Evidence("No supporting records", "No notification or mandate backs this up yet.", "info", 0, 15))
    score = sum(e.points for e in ev)
    if n < 3:
        score = min(score, 74)
        ev.append(Evidence("Short history", f"Only {n} charges observed, so confidence is capped at Medium.", "warn"))
    s.evidence = ev
    s.confidence_score = round(score)
    s.confidence_label = "High" if score >= 75 else "Medium" if score >= 50 else "Low"


# ------------------------------------------------------------------ mandates
def find_mandate_findings(mandates, series, reference, today) -> list:
    subs = [s for s in series if s.category == "subscription"]
    out = []
    for m in mandates:
        if m.status != "active":
            continue
        per_year = CADENCES[m.frequency][2]
        svc, _, how = identify_service(m.raw_merchant, reference)
        linked = next((s for s in subs if (svc and s.service == svc) or _same_merchant(m.raw_merchant, s)), None)
        exposure = m.amount * per_year
        if linked is None and svc is None:
            ev = [Evidence("Authorisation is active", f"{inr(m.amount)}/{m.frequency} via {m.method}, created {m.created:%d %b %Y}.", "info"),
                  Evidence("Raw merchant identifier", f"'{m.raw_merchant}' does not match anything in the reference list.", "warn"),
                  Evidence("Matching transactions", "No transaction in the statement history matches this merchant."
                           + ("" if m.last_debit else " No debit has ever been recorded under it."), "warn")]
            for s in subs:                                    # weak, amount-only leads
                if s.current_amount == m.amount and s.cadence == m.frequency:
                    other = f" It already has its own mandate ({s.mandate.mandate_id}), so this is probably not it." if s.mandate else ""
                    ev.append(Evidence("Weak lead (amount only)",
                                       f"{s.display_name} also costs {inr(m.amount)}/{m.frequency}, but the merchant name is different.{other}", "info"))
            out.append(MandateFinding(
                m, "orphan", None, f"Unidentified active payment authorisation: {inr(m.amount)}/{PERIOD_WORD[m.frequency]}", ev,
                ["Which company this mandate belongs to", "Whether any debit has actually happened under it",
                 "Which app or website you approved it from"],
                ["Open your UPI app and find this mandate in the AutoPay / mandates section.",
                 "Note the merchant name, mandate reference and the app it was created from.",
                 f"Search your email and SMS around {m.created:%d %b %Y} for a sign-up or approval message.",
                 "Check app-store and card subscription lists for anything costing the same amount.",
                 "If you still can't identify it, pause or revoke it in your UPI app.",
                 "Save a screenshot of the status afterwards and re-check after the next expected debit date."],
                exposure))
        elif svc and (linked is None or linked.status == "stopped"):
            last = linked.txns[-1].date if linked else None
            ev = [Evidence("Authorisation is active", f"{inr(m.amount)}/{m.frequency} via {m.method}, created {m.created:%d %b %Y}.", "info"),
                  Evidence("Service recognised", f"Matched to {svc} ({how}).", "ok"),
                  Evidence("Charges have stopped",
                           f"Last charge was {last:%d %b %Y} ({(today - last).days} days ago)." if last else "No charges found.", "warn")]
            out.append(MandateFinding(
                m, "dormant", svc, f"{svc} stopped charging, but its mandate is still active", ev,
                ["Whether the subscription was cancelled on the service side", "Whether the service can still debit you"],
                [f"Check {svc}'s billing page to confirm the subscription is cancelled.",
                 "Open your UPI app and revoke the mandate if it is no longer needed.",
                 "Keep the confirmation of both steps."],
                exposure))
        else:
            out.append(MandateFinding(m, "linked", svc or linked.service, f"{linked.display_name} mandate matches its charges",
                                      [], [], [], 0))
    return out


# ------------------------------------------------------------------ alerts
def build_alerts(series, findings) -> list:
    alerts = []
    for f in findings:
        if f.kind == "orphan":
            alerts.append(Alert(1, "orphan_mandate", f.headline,
                                "Cannot be matched to any recognised service. Investigate before the next debit.",
                                f.annual_exposure, f.mandate.mandate_id))
        elif f.kind == "dormant":
            alerts.append(Alert(2, "dormant_mandate", f.headline,
                                "Charges stopped, but the authorisation could allow future debits.",
                                f.annual_exposure, f.mandate.mandate_id))
    for s in series:
        if s.category != "subscription" or s.status != "active":
            continue
        if s.trial:
            alerts.append(Alert(3, "trial_conversion", f"{s.display_name}: possible free-trial conversion",
                                f"A trial-ending notice on {s.trial['notice'].date:%d %b} was followed by the first "
                                f"{inr(s.trial['amount'])} charge on {s.trial['first_charge']:%d %b}.",
                                s.annual_cost_estimate, s.display_name))
        if s.price_change and s.price_change["diff"] > 0:
            pc = s.price_change
            alerts.append(Alert(4, "price_increase", f"{s.display_name}: price increase",
                                f"{inr(pc['previous'])} to {inr(pc['new'])} per {PERIOD_WORD[s.cadence]}; "
                                f"about {inr(pc['annual_impact'])} extra per year if it continues.",
                                pc["annual_impact"], s.display_name))
        if s.unused:
            alerts.append(Alert(5, "unused", f"{s.display_name}: may be unused",
                                f"No activity recorded for {s.unused['idle_days']} days. Review it; "
                                "usage data is not proof you don't need it.",
                                s.annual_cost_estimate, s.display_name))
    return sorted(alerts, key=lambda a: (a.priority, -a.annual_impact))


# ------------------------------------------------------------------ savings simulator
def simulate_savings(subs, decisions, downgrade_price, today) -> dict:
    """decisions: {service: 'keep' | 'downgrade' | 'cancel'}. All figures are estimates."""
    rows, annual_total, next12_total = [], 0, 0
    for s in subs:
        action = decisions.get(s.display_name, "keep")
        new_price = {"keep": s.current_amount, "downgrade": downgrade_price.get(s.display_name, s.current_amount),
                     "cancel": 0}[action]
        per_charge = s.current_amount - new_price
        steady = per_charge * s.per_year
        count, d = 0, s.next_renewal
        while action != "keep" and d and d <= today + timedelta(days=365):
            count += 1
            d = advance(d, s.cadence)
        rows.append(dict(service=s.display_name, action=action, current=s.current_amount, new=new_price,
                         steady_annual=steady, next_renewal=s.next_renewal,
                         charges_avoided_next_12m=count, next_12m=per_charge * count))
        annual_total += steady
        next12_total += per_charge * count
    return dict(rows=rows, annual=annual_total, monthly=annual_total / 12, six_months=annual_total / 2,
                next_12_months=next12_total)


def upcoming_charges(series, today, days=30) -> list:
    out = [(s.next_renewal, s.display_name, s.current_amount) for s in series
           if s.category == "subscription" and s.status == "active" and s.next_renewal
           and today <= s.next_renewal <= today + timedelta(days=days)]
    return sorted(out)
