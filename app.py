"""QuietLeak - Streamlit dashboard.  Run:  streamlit run app.py"""
import pandas as pd
import streamlit as st

import data
import engine
from guidance import CHECKLISTS, DISCLAIMER, METHODS, STATUSES, recommended_next_step
from models import inr

st.set_page_config(page_title="QuietLeak", page_icon="💧", layout="wide")

# ---------------------------------------------------------------- analysis (pure Python, see engine.py)
TODAY = data.TODAY
TXNS, MANDATES = data.transactions(), data.mandates()
SERIES = engine.analyse(TXNS, data.REFERENCE, data.notifications(), data.usage(), MANDATES, TODAY)
FINDINGS = engine.find_mandate_findings(MANDATES, SERIES, data.REFERENCE, TODAY)
ALERTS = engine.build_alerts(SERIES, FINDINGS)
SUBS = [s for s in SERIES if s.category == "subscription"]
ACTIVE = [s for s in SUBS if s.status == "active"]
BY_NAME = {s.display_name: s for s in SUBS}
ICON = {"ok": "✅", "warn": "⚠️", "info": "ℹ️"}
ALERT_ICON = {"orphan_mandate": "🔎", "dormant_mandate": "💤", "trial_conversion": "🎟️",
              "price_increase": "📈", "unused": "📴"}

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("💧 QuietLeak")
    st.caption("Find the recurring payments nobody can find.")
    st.info("All data is **fictional** (persona: Aarav). QuietLeak never connects to a bank "
            "and never cancels anything for you.")
    st.write(f"Demo date: **{TODAY:%d %b %Y}**")
    with st.expander("Peek at the synthetic data"):
        st.write("Transactions")
        st.dataframe(pd.DataFrame([{"date": t.date, "description": t.raw, "amount": t.amount} for t in TXNS]),
                     hide_index=True)
        st.write("Payment mandates")
        st.dataframe(pd.DataFrame([vars(m) for m in MANDATES]), hide_index=True)

st.title("QuietLeak")
st.caption("Discover recurring payments, understand what they cost, and decide what to do. "
           "Every flag shows its evidence.")

tabs = st.tabs(["Overview", "Recurring payments", "Orphan mandates", "Not flagged (and why)",
                "Savings simulator", "Cancellation helper"])

# ---------------------------------------------------------------- 1. overview
with tabs[0]:
    est_year = sum(s.current_amount * s.per_year for s in ACTIVE)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Active recurring payments", len(ACTIVE))
    c2.metric("Estimated yearly cost", inr(est_year), help="Estimate: today's price x charges per year. Not money already spent.")
    c3.metric("Items needing attention", len(ALERTS))
    c4.metric("Unidentified mandates", sum(f.kind == "orphan" for f in FINDINGS))

    st.subheader("Needs attention (most urgent first)")
    for a in ALERTS:
        with st.container(border=True):
            st.markdown(f"**{ALERT_ICON[a.kind]} {a.title}**")
            st.write(a.detail)
            label = "Extra cost per year (estimate)" if a.kind == "price_increase" else "Yearly cost involved (estimate)"
            st.caption(f"{label}: {inr(a.annual_impact)}")

    st.subheader("Expected charges in the next 30 days")
    up = engine.upcoming_charges(SERIES, TODAY)
    st.dataframe(pd.DataFrame([{"Expected date": d, "Service": n, "Amount": inr(a)} for d, n, a in up]), hide_index=True)

# ---------------------------------------------------------------- 2. recurring payments
with tabs[1]:
    st.dataframe(pd.DataFrame([{
        "Service": s.display_name, "Rhythm": s.cadence, "Price": inr(s.current_amount),
        "Est. yearly cost": inr(s.annual_cost_estimate) if s.status == "active" else "stopped",
        "Confidence": f"{s.confidence_label} ({s.confidence_score:.0f})",
        "Flags": ", ".join(f for f, on in [("price increase", s.price_change and s.price_change["diff"] > 0),
                                          ("trial conversion", s.trial), ("maybe unused", s.unused)] if on),
    } for s in SUBS]), hide_index=True)

    name = st.selectbox("Open a payment to see why it was flagged", list(BY_NAME), key="detail_pick")
    s = BY_NAME[name]
    st.subheader(f"{s.display_name}  ·  {s.status}")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Current price", f"{inr(s.current_amount)} / {engine.PERIOD_WORD[s.cadence]}")
    m2.metric("Estimated yearly cost", inr(s.annual_cost_estimate), help="ESTIMATE: current price x charges per year.")
    m3.metric("Actually paid, last 12 months", inr(s.spent_last_12m), help="ACTUAL: sum of observed charges.")
    m4.metric("Next expected charge", f"{s.next_renewal:%d %b %Y}" if s.next_renewal else "none expected")

    left, right = st.columns([3, 2])
    with left:
        with st.container(border=True):
            st.markdown("**Why we flagged this payment**")
            for e in s.evidence:
                st.markdown(f"{ICON[e.status]} **{e.label}**  \n{e.detail}")
            st.progress(min(s.confidence_score / 100, 1.0), text=f"Confidence: {s.confidence_label} ({s.confidence_score:.0f}/100)")
            if s.confidence_label != "High":
                st.caption("Not High, so treat this as a lead to verify, not a fact.")
    with right:
        if s.price_change and s.price_change["diff"] > 0:
            pc = s.price_change
            st.warning(f"**Price increase.** {inr(pc['previous'])} → {inr(pc['new'])} since {pc['since']:%d %b %Y}. "
                       f"About **{inr(pc['annual_impact'])}** extra per year if it continues."
                       + (f"\n\nSupported by notice: _{pc['notice'].text}_" if pc["notice"] else ""))
        if s.trial:
            st.warning(f"**Possible trial-to-paid conversion.** Notice on {s.trial['notice'].date:%d %b}: "
                       f"_{s.trial['notice'].text}_ First paid charge: {s.trial['first_charge']:%d %b}. "
                       "A bank line alone could not prove this; the notification does.")
        if s.unused:
            st.warning(f"**May be unused.** No activity for {s.unused['idle_days']} days "
                       f"(last active {s.unused['last_active']:%d %b %Y}). Please review. This is a prompt, not a verdict.")
        if s.mandate:
            st.info(f"Linked mandate {s.mandate.mandate_id}: {inr(s.mandate.amount)}/{s.mandate.frequency} via {s.mandate.method}.")
        st.caption("Statement descriptions seen: " + ", ".join(f"`{r}`" for r in s.raw_descriptions))

    st.write("Charge history")
    hist = pd.DataFrame({"date": [t.date for t in s.txns], "amount (₹)": [t.amount for t in s.txns]}).set_index("date")
    st.bar_chart(hist)

# ---------------------------------------------------------------- 3. orphan mandates
with tabs[2]:
    st.write("Payment authorisations that are **active but can't be confidently tied to a service you recognise**, "
             "or that outlived the subscription they were created for.")
    issues = [f for f in FINDINGS if f.kind != "linked"]
    for f in issues:
        with st.container(border=True):
            st.subheader(("🔎 " if f.kind == "orphan" else "💤 ") + f.headline)
            st.caption(f"Mandate {f.mandate.mandate_id} · yearly exposure if it keeps running: {inr(f.annual_exposure)} (estimate)")
            for e in f.evidence:
                st.markdown(f"{ICON[e.status]} **{e.label}**  \n{e.detail}")
            st.markdown("**What we don't know:** " + "; ".join(f.missing) + ".")
            st.markdown("**Investigation checklist**")
            done = 0
            for i, step in enumerate(f.checklist):
                done += st.checkbox(step, key=f"inv_{f.mandate.mandate_id}_{i}")
            st.progress(done / len(f.checklist), text=f"{done} of {len(f.checklist)} steps")
    st.write("Mandates that line up with real charges")
    st.dataframe(pd.DataFrame([{"Mandate": f.mandate.mandate_id, "Merchant": f.mandate.raw_merchant,
                                "Amount": inr(f.mandate.amount), "Matched to": f.service}
                               for f in FINDINGS if f.kind == "linked"]), hide_index=True)

# ---------------------------------------------------------------- 4. not flagged
with tabs[3]:
    st.write("Repeating payments are **not** automatically subscriptions. Here is what we chose not to flag, and why.")
    skipped = [s for s in SERIES if s.category != "subscription"]
    st.dataframe(pd.DataFrame([{
        "Merchant": s.display_name, "Payments": len(s.txns),
        "Paid, last 12 months": inr(s.spent_last_12m),
        "Treated as": s.category.replace("_", " "), "Why": s.reason} for s in skipped]), hide_index=True)

# ---------------------------------------------------------------- 5. savings simulator
with tabs[4]:
    st.write("Pick what you'd do with each active subscription. Figures are **estimates**, not guaranteed savings. "
             "Downgrade prices are fictional.")
    decisions = {}
    for s in ACTIVE:
        a, b, c = st.columns([2, 3, 2])
        a.write(f"**{s.display_name}**  \n{inr(s.current_amount)}/{engine.PERIOD_WORD[s.cadence]}")
        decisions[s.display_name] = b.radio("Decision", ["keep", "downgrade", "cancel"], horizontal=True,
                                            key=f"sim_{s.display_name}", label_visibility="collapsed")
        alt = data.DOWNGRADE_PRICE.get(s.display_name)
        c.caption(f"Downgrade plan: {inr(alt)}" if alt else "")
    res = engine.simulate_savings(ACTIVE, decisions, data.DOWNGRADE_PRICE, TODAY)
    st.divider()
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Potential monthly saving", inr(res["monthly"]))
    k2.metric("Potential yearly saving", inr(res["annual"]))
    k3.metric("Over six months", inr(res["six_months"]))
    k4.metric("Next 12 months, billing-cycle aware", inr(res["next_12_months"]),
              help="Counts only renewals that fall after each service's next renewal date. You've already paid for the current cycle.")
    changed = [r for r in res["rows"] if r["action"] != "keep"]
    if changed:
        st.dataframe(pd.DataFrame([{
            "Service": r["service"], "Decision": r["action"], "Now": inr(r["current"]), "After": inr(r["new"]),
            "Steady yearly saving": inr(r["steady_annual"]), "Savings start": r["next_renewal"],
            "Renewals avoided (12 mo)": r["charges_avoided_next_12m"], "Saved in next 12 mo": inr(r["next_12m"])}
            for r in changed]), hide_index=True)
    st.caption("Assumes prices stay the same and the change succeeds. Cancellation fees or notice periods, "
               "if any, are not included. Check the service's terms.")

# ---------------------------------------------------------------- 6. cancellation helper
with tabs[5]:
    st.write("QuietLeak explains the steps and tracks your progress. **You** do the cancelling with the service or your bank.")
    pick = st.selectbox("Which payment do you want to stop?", list(BY_NAME), key="cx_pick")
    default = data.PAYMENT_METHOD.get(pick, METHODS[0])
    method = st.radio("How is it paid?", METHODS, index=METHODS.index(default), key=f"method_{pick}")
    col1, col2 = st.columns(2)
    sub_done = col1.checkbox("I've cancelled the subscription with the service", key=f"subdone_{pick}")
    mandate_done = False
    if method != "App store billing":
        mandate_done = col2.checkbox("I've revoked the payment mandate / card instruction", key=f"mandone_{pick}")

    with st.container(border=True):
        st.markdown("**📋 QuietLeak's recommended next step**")
        st.write(recommended_next_step(method, sub_done, mandate_done))
        st.caption(DISCLAIMER)

    st.markdown("**Checklist**")
    steps = CHECKLISTS[method]
    n_done = sum(st.checkbox(step, key=f"chk_{pick}_{method}_{i}") for i, step in enumerate(steps))
    st.progress(n_done / len(steps), text=f"{n_done} of {len(steps)} steps ticked")

    status = st.selectbox("Cancellation status", STATUSES, key=f"status_{pick}")
    if status.startswith("Completed"):
        st.warning("This only records what you tell us. It does not prove the cancellation worked. "
                   "Keep the confirmation and check your next statement.")

    st.markdown("**Progress across all subscriptions**")
    st.dataframe(pd.DataFrame([{"Service": n, "Status": st.session_state.get(f"status_{n}", STATUSES[0])}
                               for n in BY_NAME]), hide_index=True)
