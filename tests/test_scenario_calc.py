"""Focused tests for scripts/scenario_calc.py. Standard library only.

Expected values in the tiny hand-made fixtures below were worked out on paper
(see the comment above each), not by running the implementation.
Run: python -m unittest discover -s tests -v
"""

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import scenario_calc as sc  # noqa: E402


def row(**overrides):
    base = {
        "quote_id": "QUO-9000", "opportunity_id": "OPP-9000", "order_id": None,
        "quote_requested_at": "2026-01-05T08:00:00Z", "quote_issued_at": "2026-01-05T20:00:00Z",
        "quote_outcome": "lost", "quoted_quantity": 0, "ordered_quantity": 0, "shipped_quantity": 0,
        "opportunity_outcome": "lost", "opportunity_closed_at": "2026-01-10T08:00:00Z",
    }
    base.update(overrides)
    return base


class RemainingQuantityTests(unittest.TestCase):
    def test_remaining_is_ordered_minus_shipped(self):
        self.assertEqual(sc.remaining_order_quantity(5, 2), 3)  # 5 - 2 by hand
        self.assertEqual(sc.remaining_order_quantity(2, 1), 1)  # the scenario
        self.assertEqual(sc.remaining_order_quantity(2, 2), 0)  # fully shipped
        self.assertEqual(sc.remaining_order_quantity(0, 0), 0)

    def test_missing_quantity_is_an_error_not_zero(self):
        with self.assertRaisesRegex(ValueError, "shipped_quantity is missing"):
            sc.remaining_order_quantity(2, None)
        with self.assertRaisesRegex(ValueError, "ordered_quantity is missing"):
            sc.remaining_order_quantity(None, 0)

    def test_invalid_quantities_are_errors(self):
        for ordered, shipped in [(2, 3), (-1, 0), (2, -1), (2, 1.5), (True, 0)]:
            with self.subTest(ordered=ordered, shipped=shipped):
                with self.assertRaises(ValueError):
                    sc.remaining_order_quantity(ordered, shipped)


class MetricTests(unittest.TestCase):
    # Fixture worked by hand:
    #   A: quoted 10, ordered 6, shipped 6, won,  request->issue 12 h
    #   B: quoted 10, ordered 0, shipped 0, lost, 36 h
    #   C: quoted  5, open (undecided), no request time
    #   D: quoted  8, ordered 4, shipped 1, won,  request->issue 24 h
    # conversion (decided A,B,D): (6+0+4)/(10+10+8) = 10/28; open C excluded
    # fill rate (orders A,D): (6+1)/(6+4) = 7/10; backlog: 0 + 3 = 3 units
    # turnaround (A,B,D): sorted 12, 24, 36 -> median 24, mean 24; C excluded
    # win rate: won A,D = 2 of closed A,B,D = 3; C open excluded
    def setUp(self):
        # Each quote belongs to its own opportunity (distinct opportunity_id), as in the data model.
        self.rows = [
            row(quote_id="QUO-9001", opportunity_id="OPP-9001", order_id="SO-9001", quote_outcome="accepted",
                quoted_quantity=10,
                ordered_quantity=6, shipped_quantity=6, opportunity_outcome="won",
                quote_requested_at="2026-02-02T08:00:00Z", quote_issued_at="2026-02-02T20:00:00Z"),
            row(quote_id="QUO-9002", opportunity_id="OPP-9002", quoted_quantity=10,
                quote_requested_at="2026-02-03T00:00:00Z", quote_issued_at="2026-02-04T12:00:00Z"),
            row(quote_id="QUO-9003", opportunity_id="OPP-9003", quote_outcome="open", opportunity_outcome="open",
                quoted_quantity=5,
                quote_requested_at=None),
            row(quote_id="QUO-9004", opportunity_id="OPP-9004", order_id="SO-9004",
                quote_outcome="partially_accepted", quoted_quantity=8,
                ordered_quantity=4, shipped_quantity=1, opportunity_outcome="won",
                quote_requested_at="2026-02-05T10:00:00Z", quote_issued_at="2026-02-06T10:00:00Z"),
        ]

    def test_conversion_excludes_open_quotes(self):
        result = sc.quote_to_order_conversion(self.rows)
        self.assertEqual((result["numerator_ordered_units"], result["denominator_quoted_units_decided"]), (10, 28))
        self.assertAlmostEqual(result["rate"], 10 / 28)
        self.assertEqual(result["excluded_open_quotes"], 1)

    def test_fill_rate_uses_orders_only(self):
        result = sc.order_fill_rate(self.rows)
        self.assertEqual((result["numerator_shipped_units"], result["denominator_ordered_units"]), (7, 10))
        self.assertAlmostEqual(result["rate"], 0.7)

    def test_backlog_sums_remaining_and_values_only_with_a_price(self):
        self.assertEqual(sc.backlog_units(self.rows)["units"], 3)
        self.assertIsNone(sc.backlog_units(self.rows)["value"])
        self.assertEqual(str(sc.backlog_units(self.rows, 100.00)["value"]), "300.0")

    def test_turnaround_excludes_and_counts_missing_request_time(self):
        result = sc.quotation_turnaround_hours(self.rows)
        self.assertEqual(result["quotes_measured"], 3)
        self.assertEqual(result["excluded_missing_request_time"], 1)
        self.assertEqual(result["median_hours"], 24)
        self.assertEqual(result["mean_hours"], 24)

    def test_turnaround_issue_before_request_is_an_error(self):
        bad = [row(quote_requested_at="2026-02-02T10:00:00Z", quote_issued_at="2026-02-02T09:00:00Z")]
        with self.assertRaises(ValueError):
            sc.quotation_turnaround_hours(bad)

    def test_win_rate_excludes_open(self):
        result = sc.opportunity_win_rate(self.rows)
        self.assertEqual((result["won"], result["closed"], result["excluded_open"]), (2, 3, 1))
        self.assertAlmostEqual(result["rate"], 2 / 3)

    def test_empty_population_is_none_not_zero(self):
        self.assertIsNone(sc.quote_to_order_conversion([])["rate"])
        self.assertIsNone(sc.order_fill_rate([])["rate"])
        self.assertIsNone(sc.opportunity_win_rate([])["rate"])
        self.assertIsNone(sc.quotation_turnaround_hours([])["median_hours"])
        only_open = [row(quote_outcome="open", opportunity_outcome="open", quoted_quantity=3)]
        self.assertIsNone(sc.quote_to_order_conversion(only_open)["rate"])

    def test_fill_rate_rejects_missing_shipped_quantity(self):
        broken = [row(order_id="SO-9999", ordered_quantity=2, shipped_quantity=None)]
        with self.assertRaises(ValueError):
            sc.order_fill_rate(broken)


class ScenarioFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(sc.DEFAULT_PATH.read_text(encoding="utf-8"))

    def test_json_example_is_consistent(self):
        self.assertEqual(sc.check_scenario(self.data), [])

    def test_scenario_quantities(self):
        s = self.data["quantity_summary_at_snapshot"]
        self.assertEqual((s["quoted_quantity"], s["ordered_quantity"], s["shipped_quantity"],
                          s["remaining_order_quantity"]), (4, 2, 1, 1))

    def test_scenario_metrics_match_hand_calculation(self):
        # 2/4 conversion, 1/2 fill, 2-1=1 unit at 1850.00, 30 h, derived on paper from the JSON dates.
        report = sc.summarize(self.data)
        scenario = report["scenario"]
        self.assertEqual(scenario["remaining_order_quantity"], 1)
        self.assertAlmostEqual(scenario["quote_to_order_conversion"]["rate"], 0.5)
        self.assertAlmostEqual(scenario["order_fill_rate"]["rate"], 0.5)
        self.assertEqual(str(scenario["backlog"]["value"]), "1850.0")
        self.assertEqual(scenario["quotation_turnaround"]["median_hours"], 30)
        cohort = report["cohort"]
        self.assertAlmostEqual(cohort["quote_to_order_conversion"]["rate"], 5 / 18)
        self.assertAlmostEqual(cohort["order_fill_rate"]["rate"], 4 / 5)
        self.assertEqual(cohort["quotation_turnaround"]["median_hours"], 27)
        self.assertAlmostEqual(cohort["opportunity_win_rate"]["rate"], 2 / 4)

    def test_consistency_check_detects_breakage(self):
        """Each mutation must be caught; a checker that cannot fail proves nothing."""

        def mutated(change):
            data = copy.deepcopy(self.data)
            change(data)
            return sc.check_scenario(data)

        cases = {
            "wrong remaining": lambda d: d["sales_order"]["lines"][0].update(remaining_order_quantity=2),
            "wrong quote amount": lambda d: d["quote"]["lines"][0].update(quoted_amount=7000.00),
            "quote reserves stock": lambda d: d["quote"]["lines"][0].update(reserves_stock=True),
            "double counted demand": lambda d: d["demand_signals"]["rows"][0].update(counts_toward_committed_demand=True),
            "reserved exceeds on hand": lambda d: d["inventory"]["stock_history"][1].update(reserved=3),
            "shipment mismatch": lambda d: d["shipments"][0]["lines"][0].update(shipped_quantity=2),
            "walkthrough demand changes": lambda d: d["changed_condition_walkthrough"]["after"].update(ordered_quantity=3),
            "cohort drifts from scenario": lambda d: d["illustrative_cohort"]["rows"][0].update(quoted_quantity=5),
        }
        for label, change in cases.items():
            with self.subTest(label):
                self.assertNotEqual(mutated(change), [], f"{label} was not detected")

    def test_missing_field_raises_instead_of_defaulting(self):
        data = copy.deepcopy(self.data)
        del data["sales_order"]["lines"][0]["shipped_quantity"]
        with self.assertRaises(KeyError):
            sc.check_scenario(data)


CLI = ROOT / "scripts" / "scenario_calc.py"
PERIOD = {"period_start": "2026-03-01T00:00:00Z", "period_end": "2026-03-20T17:00:00Z"}


def opp_row(opportunity_id, outcome, closed_at, quote_id="QUO-9100"):
    return row(quote_id=quote_id, opportunity_id=opportunity_id, opportunity_outcome=outcome,
               opportunity_closed_at=closed_at)


def run_cli_on_copy(mutate):
    """Run the real CLI on a temporary copy of the scenario; the committed example is never touched."""
    data = json.loads(sc.DEFAULT_PATH.read_text(encoding="utf-8"))
    mutate(data)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "scenario-copy.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return subprocess.run([sys.executable, str(CLI), str(path)], capture_output=True, text=True,
                              encoding="utf-8")


def cohort_line(stdout, metric):
    """The printed line for `metric` inside the [cohort] section of the CLI output."""
    section = stdout.split("[cohort]", 1)[1]
    return next(line.strip() for line in section.splitlines() if line.strip().startswith(metric + ":"))


def cohort_row(data, quote_id):
    return next(r for r in data["illustrative_cohort"]["rows"] if r["quote_id"] == quote_id)


class WinRateRegressionTests(unittest.TestCase):
    """Review findings 1 and 2: docs/business-metrics.md section 5 and the Opportunity relationship."""

    def test_blank_or_non_text_opportunity_ids_are_errors(self):
        for value in ("", "   ", 0, True, []):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "opportunity_id"):
                sc.opportunity_win_rate([opp_row(value, "won", "2026-03-05T09:00:00Z")])

    def test_reversed_period_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "period_start"):
            sc.opportunity_win_rate(
                [opp_row("OPP-9001", "won", "2026-03-05T09:00:00Z")],
                period_start="2026-03-20T00:00:00Z", period_end="2026-03-01T00:00:00Z")

    # Finding 1 (a): QUO-2002's opportunity has a null close date. Closed opportunities are then
    # OPP-1001 won, OPP-1003 lost, OPP-1005 lost = 3, won 1, so 1/3; OPP-1002 is excluded and reported.
    def test_cli_null_close_date_is_excluded_and_reported(self):
        result = run_cli_on_copy(lambda d: cohort_row(d, "QUO-2002").update(opportunity_closed_at=None))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Consistency checks: PASS", result.stdout)
        line = cohort_line(result.stdout, "opportunity_win_rate")
        self.assertIn("won=1", line)
        self.assertIn("closed=3", line)
        self.assertIn("rate=0.3333", line)
        self.assertIn("excluded_missing_close_date=1", line)
        self.assertIn("OPP-1002", line)

    # Finding 2 (b): two quote rows for one won opportunity plus one lost opportunity: 1 won of 2, not 2 of 3.
    def test_two_quotes_for_one_opportunity_count_once(self):
        rows = [
            opp_row("OPP-9100", "won", "2026-03-05T09:00:00Z", quote_id="QUO-9101"),
            opp_row("OPP-9100", "won", "2026-03-05T09:00:00Z", quote_id="QUO-9102"),
            opp_row("OPP-9200", "lost", "2026-03-06T09:00:00Z", quote_id="QUO-9201"),
        ]
        result = sc.opportunity_win_rate(rows)
        self.assertEqual((result["won"], result["closed"]), (1, 2))
        self.assertAlmostEqual(result["rate"], 0.5)

    def test_cli_duplicate_opportunity_row_does_not_change_the_published_rate(self):
        def add_second_quote(data):
            extra = dict(cohort_row(data, "QUO-2002"), quote_id="QUO-2006")
            data["illustrative_cohort"]["rows"].append(extra)

        result = run_cli_on_copy(add_second_quote)
        self.assertEqual(result.returncode, 0, result.stderr)
        line = cohort_line(result.stdout, "opportunity_win_rate")
        self.assertIn("won=2", line)
        self.assertIn("closed=4", line)
        self.assertIn("rate=0.5", line)

    # Finding 2 (c): rows for one opportunity that disagree must be an error, not a silent pick.
    def test_inconsistent_duplicate_outcome_is_a_clear_error(self):
        rows = [opp_row("OPP-9100", "won", "2026-03-05T09:00:00Z", quote_id="QUO-9101"),
                opp_row("OPP-9100", "lost", "2026-03-05T09:00:00Z", quote_id="QUO-9102")]
        with self.assertRaisesRegex(ValueError, r"OPP-9100.*conflicting"):
            sc.opportunity_win_rate(rows)

    def test_inconsistent_duplicate_close_date_is_a_clear_error(self):
        rows = [opp_row("OPP-9100", "won", "2026-03-05T09:00:00Z", quote_id="QUO-9101"),
                opp_row("OPP-9100", "won", "2026-03-07T09:00:00Z", quote_id="QUO-9102")]
        with self.assertRaisesRegex(ValueError, r"OPP-9100.*conflicting"):
            sc.opportunity_win_rate(rows)

    def test_cli_inconsistent_duplicate_exits_with_clear_error(self):
        def add_conflicting_quote(data):
            extra = dict(cohort_row(data, "QUO-2002"), quote_id="QUO-2006", opportunity_outcome="lost")
            data["illustrative_cohort"]["rows"].append(extra)

        result = run_cli_on_copy(add_conflicting_quote)
        self.assertEqual(result.returncode, 1)
        self.assertIn("OPP-1002", result.stderr)
        self.assertIn("conflicting", result.stderr)

    # Documented rule: close date must fall in the period, inclusive at both ends.
    def test_close_date_outside_period_is_excluded_and_reported(self):
        rows = [
            opp_row("OPP-9001", "won", "2026-03-01T00:00:00Z"),    # on the first instant: eligible
            opp_row("OPP-9002", "lost", "2026-03-20T17:00:00Z"),   # on the snapshot: eligible
            opp_row("OPP-9003", "won", "2026-02-28T23:59:59Z"),    # before the period
            opp_row("OPP-9004", "lost", "2026-03-20T17:00:01Z"),   # after the snapshot
        ]
        result = sc.opportunity_win_rate(rows, **PERIOD)
        self.assertEqual((result["won"], result["closed"], result["excluded_outside_period"]), (1, 2, 2))
        self.assertAlmostEqual(result["rate"], 0.5)

    def test_missing_close_date_is_excluded_even_without_a_period(self):
        rows = [opp_row("OPP-9001", "won", None), opp_row("OPP-9002", "lost", "2026-03-05T09:00:00Z")]
        result = sc.opportunity_win_rate(rows)
        self.assertEqual((result["won"], result["closed"]), (0, 1))
        self.assertEqual(result["excluded_missing_close_date"], 1)
        self.assertEqual(result["excluded_missing_close_date_ids"], ["OPP-9001"])

    def test_all_closed_opportunities_unusable_gives_none_not_zero(self):
        result = sc.opportunity_win_rate([opp_row("OPP-9001", "won", None)])
        self.assertIsNone(result["rate"])

    def test_unknown_outcome_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "OPP-9001"):
            sc.opportunity_win_rate([opp_row("OPP-9001", "wno", "2026-03-05T09:00:00Z")])

    def test_missing_opportunity_id_is_an_error(self):
        with self.assertRaises(ValueError):
            sc.opportunity_win_rate([opp_row(None, "won", "2026-03-05T09:00:00Z")])

    def test_committed_example_published_numbers_are_unchanged(self):
        """The five-row cohort has no missing close dates, so its published numbers must not move."""
        result = subprocess.run([sys.executable, str(CLI)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        line = cohort_line(result.stdout, "opportunity_win_rate")
        for expected in ("won=2", "closed=4", "rate=0.5", "excluded_open=1",
                         "excluded_missing_close_date=0", "excluded_outside_period=0"):
            self.assertIn(expected, line)
        self.assertIn("rate=0.2778", cohort_line(result.stdout, "quote_to_order_conversion"))
        self.assertIn("rate=0.8", cohort_line(result.stdout, "order_fill_rate"))
        self.assertIn("median_hours=27", cohort_line(result.stdout, "quotation_turnaround"))


if __name__ == "__main__":
    unittest.main()
