import unittest
from datetime import date

import data
from engine import analyse, build_alerts, find_mandate_findings, simulate_savings, upcoming_charges
from guidance import recommended_next_step

T = data.TODAY
SERIES = analyse(data.transactions(), data.REFERENCE, data.notifications(), data.usage(), data.mandates(), T)
BY = {s.display_name: s for s in SERIES}
FINDINGS = find_mandate_findings(data.mandates(), SERIES, data.REFERENCE, T)
SUBS = [s for s in SERIES if s.category == "subscription"]


class Detection(unittest.TestCase):
    def test_subscriptions_found(self):
        self.assertEqual({s.display_name for s in SUBS},
                         {"MusicApp", "VideoStream", "CloudStore", "LearnApp", "FitnessPlus", "DailyNews", "FitZone"})

    def test_cadences(self):
        self.assertEqual(BY["MusicApp"].cadence, "monthly")
        self.assertEqual(BY["FitnessPlus"].cadence, "quarterly")
        self.assertEqual(BY["DailyNews"].cadence, "annual")

    def test_false_positives_not_flagged(self):
        self.assertEqual(BY["SWIGGY*ORDER"].category, "not_recurring")
        self.assertEqual(BY["BIGBASKET"].category, "not_recurring")
        self.assertEqual(BY["RENT TRANSFER SHARMA"].category, "fixed_obligation")
        self.assertEqual(BY["BSES ELECTRICITY BILL"].category, "variable_bill")

    def test_stopped_subscription(self):
        self.assertEqual(BY["FitZone"].status, "stopped")
        self.assertEqual(BY["MusicApp"].status, "active")
        self.assertEqual(BY["FitZone"].annual_cost_estimate, 0)   # no longer being charged


class Costs(unittest.TestCase):
    def test_price_increase(self):
        pc = BY["MusicApp"].price_change
        self.assertEqual((pc["previous"], pc["new"], pc["diff"], pc["annual_impact"]), (99, 149, 50, 600))
        self.assertIsNotNone(pc["notice"])

    def test_annual_estimates_match_the_brief(self):
        self.assertEqual(BY["MusicApp"].annual_cost_estimate, 1788)
        self.assertEqual(BY["VideoStream"].annual_cost_estimate, 3588)
        self.assertEqual(BY["LearnApp"].annual_cost_estimate, 5988)
        self.assertEqual(BY["FitnessPlus"].annual_cost_estimate, 4800)

    def test_estimate_and_actual_differ(self):
        # MusicApp: 10 charges at 99 + 2 at 149 inside the last 365 days is not 12 x 149
        self.assertNotEqual(BY["MusicApp"].spent_last_12m, BY["MusicApp"].annual_cost_estimate)
        self.assertEqual(BY["VideoStream"].spent_last_12m, 598)


class Evidence(unittest.TestCase):
    def test_trial_needs_notification(self):
        self.assertIsNotNone(BY["VideoStream"].trial)
        self.assertIsNone(BY["CloudStore"].trial)

    def test_unused_needs_usage_data(self):
        self.assertEqual(BY["LearnApp"].unused["idle_days"], 164)
        self.assertIsNone(BY["MusicApp"].unused)

    def test_short_history_capped_at_medium(self):
        self.assertEqual(BY["VideoStream"].confidence_label, "Medium")
        self.assertEqual(BY["DailyNews"].confidence_label, "Medium")
        self.assertEqual(BY["CloudStore"].confidence_label, "High")


class Mandates(unittest.TestCase):
    def test_orphan_found(self):
        orphans = [f for f in FINDINGS if f.kind == "orphan"]
        self.assertEqual([f.mandate.mandate_id for f in orphans], ["M004"])
        self.assertEqual(orphans[0].annual_exposure, 5988)

    def test_orphan_weak_lead_is_explained_away(self):
        text = " ".join(e.detail for e in [f for f in FINDINGS if f.kind == "orphan"][0].evidence)
        self.assertIn("already has its own mandate (M003)", text)

    def test_dormant_found(self):
        self.assertEqual([f.mandate.mandate_id for f in FINDINGS if f.kind == "dormant"], ["M005"])

    def test_alert_order(self):
        kinds = [a.kind for a in build_alerts(SERIES, FINDINGS)]
        self.assertEqual(kinds[0], "orphan_mandate")
        self.assertEqual(set(kinds), {"orphan_mandate", "dormant_mandate", "trial_conversion", "price_increase", "unused"})


class Savings(unittest.TestCase):
    def test_brief_example(self):
        subs = [BY["MusicApp"], BY["LearnApp"]]
        r = simulate_savings(subs, {"MusicApp": "cancel", "LearnApp": "cancel"}, data.DOWNGRADE_PRICE, T)
        self.assertEqual((r["monthly"], r["annual"], r["six_months"]), (648, 7776, 3888))

    def test_downgrade(self):
        r = simulate_savings([BY["LearnApp"]], {"LearnApp": "downgrade"}, data.DOWNGRADE_PRICE, T)
        self.assertEqual(r["annual"], (499 - 199) * 12)

    def test_billing_cycle_awareness(self):
        r = simulate_savings([BY["DailyNews"]], {"DailyNews": "cancel"}, data.DOWNGRADE_PRICE, T)
        self.assertEqual(r["rows"][0]["next_renewal"], date(2027, 10, 18))
        self.assertEqual(r["next_12_months"], 1499)

    def test_nothing_selected(self):
        self.assertEqual(simulate_savings(SUBS, {}, data.DOWNGRADE_PRICE, T)["annual"], 0)

    def test_upcoming(self):
        names = [n for _, n, _ in upcoming_charges(SERIES, T)]
        self.assertIn("LearnApp", names)
        self.assertNotIn("DailyNews", names)


class Guidance(unittest.TestCase):
    def test_matches_brief_example(self):
        self.assertTrue(recommended_next_step("Debit or credit card", False, True).startswith("Check the mandate's status"))

    def test_app_store_has_no_mandate_step(self):
        self.assertIn("no separate mandate", recommended_next_step("App store billing", True, False))


if __name__ == "__main__":
    unittest.main(verbosity=1)
