# QuietLeak (hackathon prototype)

   **Live demo:** https://quietleak.streamlit.app

![tests](../../actions/workflows/tests.yml/badge.svg)

Finds recurring payments in **fictional** bank data, explains why each was flagged, estimates yearly cost,
spots unidentified payment mandates, and walks the user through cancelling. It never cancels anything itself.

## Run
    pip install -r requirements.txt
    streamlit run app.py

## Test the logic (no Streamlit needed)
    python test_engine.py

## Files
| File | Purpose |
|---|---|
| `data.py` | Synthetic transactions, mandates, notifications, usage, plus deliberate false-positive traps |
| `engine.py` | Merchant matching, recurrence detection, confidence scoring, mandate findings, alerts, savings maths |
| `guidance.py` | Cancellation checklists and next-step text per payment method |
| `models.py` | Dataclasses and the `inr()` formatter |
| `app.py` | Streamlit dashboard (6 tabs) |
| `test_engine.py` | 21 tests, incl. the brief's numbers (₹99→₹149 = ₹600/yr, ₹648/mo = ₹7,776/yr) |

## Design rules
- Estimated yearly cost (price x charges per year) is always shown separately from actual money paid.
- Confidence is a transparent sum of evidence points. Fewer than 3 observed charges caps it at Medium.
- Trial conversion needs a notification; "unused" needs usage data. A bank line alone never claims either.
- "Completed" in the cancellation tracker is self-reported, not proof.
