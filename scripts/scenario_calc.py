"""Check and summarize the fictional order scenario.

Reads examples/fictional-order-scenario.json, verifies that its quantities and
amounts agree with each other, and computes the five metrics defined in
docs/business-metrics.md. Standard library only (Python 3.11+).

Usage:
    python scripts/scenario_calc.py [path/to/scenario.json]

Exit status is 0 when every consistency check passes and 1 otherwise.
All data is fictional.
"""

from __future__ import annotations

import json
import statistics
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "examples" / "fictional-order-scenario.json"


def remaining_order_quantity(ordered_quantity, shipped_quantity):
    """ordered_quantity - shipped_quantity. Cancellations/returns are out of scope.

    Missing values are an error, never silently zero.
    """
    for name, value in (("ordered_quantity", ordered_quantity), ("shipped_quantity", shipped_quantity)):
        if value is None:
            raise ValueError(f"{name} is missing")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} must be a non-negative integer, got {value!r}")
    if shipped_quantity > ordered_quantity:
        raise ValueError(
            f"shipped_quantity {shipped_quantity} exceeds ordered_quantity {ordered_quantity}"
        )
    return ordered_quantity - shipped_quantity


def _ratio(numerator, denominator):
    """Return numerator/denominator, or None (not 0) when the population is empty."""
    return None if denominator == 0 else numerator / denominator


def _parse(timestamp):
    return datetime.fromisoformat(timestamp)


# --- Metrics (definitions: docs/business-metrics.md) -------------------------

def quote_to_order_conversion(rows):
    """Ordered units / quoted units, over quotes whose outcome is decided (not 'open')."""
    decided = [r for r in rows if r["quote_outcome"] != "open"]
    numerator = sum(r["ordered_quantity"] for r in decided)
    denominator = sum(r["quoted_quantity"] for r in decided)
    return {
        "numerator_ordered_units": numerator,
        "denominator_quoted_units_decided": denominator,
        "rate": _ratio(numerator, denominator),
        "excluded_open_quotes": len(rows) - len(decided),
    }


def order_fill_rate(rows):
    """Cumulative shipped units / ordered units, over orders accepted by the snapshot."""
    orders = [r for r in rows if r["order_id"] is not None]
    for r in orders:
        remaining_order_quantity(r["ordered_quantity"], r["shipped_quantity"])  # validates
    numerator = sum(r["shipped_quantity"] for r in orders)
    denominator = sum(r["ordered_quantity"] for r in orders)
    return {
        "numerator_shipped_units": numerator,
        "denominator_ordered_units": denominator,
        "rate": _ratio(numerator, denominator),
    }


def backlog_units(rows, unit_price=None):
    """Sum of remaining_order_quantity over accepted orders; value only if a price is given."""
    units = sum(
        remaining_order_quantity(r["ordered_quantity"], r["shipped_quantity"])
        for r in rows
        if r["order_id"] is not None
    )
    value = None if unit_price is None else Decimal(str(unit_price)) * units
    return {"units": units, "value": value}


def quotation_turnaround_hours(rows):
    """Hours from quote request to first issue. Rows without a request time are excluded and counted."""
    hours = []
    missing = 0
    for r in rows:
        if r["quote_requested_at"] is None:
            missing += 1
            continue
        delta = (_parse(r["quote_issued_at"]) - _parse(r["quote_requested_at"])).total_seconds() / 3600
        if delta < 0:
            raise ValueError(f"{r['quote_id']} was issued before it was requested")
        hours.append(delta)
    return {
        "median_hours": statistics.median(hours) if hours else None,
        "mean_hours": statistics.fmean(hours) if hours else None,
        "quotes_measured": len(hours),
        "excluded_missing_request_time": missing,
    }


OPPORTUNITY_OUTCOMES = ("won", "lost", "open")


def _distinct_opportunities(rows):
    """One record per opportunity_id (an opportunity may have several quote rows).

    Rows for the same opportunity must agree on outcome and close date; otherwise
    raise rather than pick one.
    """
    merged = {}
    for r in rows:
        opportunity_id = r.get("opportunity_id")
        if not isinstance(opportunity_id, str) or not opportunity_id.strip():
            raise ValueError(f"quote row {r.get('quote_id')!r} has no opportunity_id")
        outcome = r["opportunity_outcome"]
        if outcome not in OPPORTUNITY_OUTCOMES:
            raise ValueError(f"opportunity {opportunity_id} has unknown outcome {outcome!r}")
        closed_at = None if r["opportunity_closed_at"] is None else _parse(r["opportunity_closed_at"])
        seen = merged.get(opportunity_id)
        if seen is None:
            merged[opportunity_id] = {"outcome": outcome, "closed_at": closed_at, "quotes": [r.get("quote_id")]}
        elif (outcome, closed_at) != (seen["outcome"], seen["closed_at"]):
            raise ValueError(
                f"opportunity {opportunity_id} has conflicting quote rows "
                f"({seen['quotes'][0]} vs {r.get('quote_id')}): outcome or close date differ"
            )
        else:
            seen["quotes"].append(r.get("quote_id"))
    return merged


def opportunity_win_rate(rows, period_start=None, period_end=None):
    """Won / (won + lost), counted per distinct opportunity, closed within the period.

    Eligible: outcome won or lost AND a close date inside [period_start, period_end]
    (inclusive; a bound of None is unbounded). Open opportunities, closed ones with no
    close date, and closed ones outside the period are excluded and reported by count
    (the last two also by id). Never silently treated as won, lost, or zero.
    """
    start = None if period_start is None else _parse(period_start)
    end = None if period_end is None else _parse(period_end)
    if start is not None and end is not None and start > end:
        raise ValueError("period_start must be on or before period_end")
    won = lost = open_count = 0
    missing_close_date, outside_period = [], []
    for opportunity_id, opp in _distinct_opportunities(rows).items():
        if opp["outcome"] == "open":
            open_count += 1
        elif opp["closed_at"] is None:
            missing_close_date.append(opportunity_id)
        elif (start is not None and opp["closed_at"] < start) or (end is not None and opp["closed_at"] > end):
            outside_period.append(opportunity_id)
        elif opp["outcome"] == "won":
            won += 1
        else:
            lost += 1
    return {
        "won": won,
        "closed": won + lost,
        "rate": _ratio(won, won + lost),
        "excluded_open": open_count,
        "excluded_missing_close_date": len(missing_close_date),
        "excluded_missing_close_date_ids": missing_close_date,
        "excluded_outside_period": len(outside_period),
        "excluded_outside_period_ids": outside_period,
    }


def scenario_row(data):
    """Build one cohort-shaped row from the main scenario records."""
    quote, order, opp = data["quote"], data["sales_order"], data["opportunity"]
    quote_line, order_line = quote["lines"][0], order["lines"][0]
    return {
        "quote_id": quote["quote_id"],
        "opportunity_id": opp["opportunity_id"],
        "order_id": order["order_id"],
        "quote_requested_at": quote["quote_requested_at"],
        "quote_issued_at": quote["issued_at"],
        "quote_outcome": quote["status"],
        "quoted_quantity": quote_line["quoted_quantity"],
        "ordered_quantity": order_line["ordered_quantity"],
        "shipped_quantity": order_line["shipped_quantity"],
        "opportunity_outcome": "won" if opp["stage"] == "closed_won" else opp["stage"],
        "opportunity_closed_at": opp["closed_at"],
    }


# --- Consistency checks ------------------------------------------------------

def check_scenario(data):
    """Return a list of human-readable problems; an empty list means the checks passed."""
    problems = []

    def expect(label, actual, expected):
        if actual != expected:
            problems.append(f"{label}: expected {expected!r}, found {actual!r}")

    price = Decimal(str(data["product"]["unit_price"]))
    quote_line = data["quote"]["lines"][0]
    order = data["sales_order"]
    order_line = order["lines"][0]

    expect("quote amount", Decimal(str(quote_line["quoted_amount"])), price * quote_line["quoted_quantity"])
    expect("order amount", Decimal(str(order_line["ordered_amount"])), price * order_line["ordered_quantity"])
    expect("order line links to quote line", order_line["quote_line_id"], quote_line["quote_line_id"])
    expect("order links to quote", order["quote_id"], data["quote"]["quote_id"])
    expect("order links to opportunity", order["opportunity_id"], data["opportunity"]["opportunity_id"])
    expect("quote links to opportunity", data["quote"]["opportunity_id"], data["opportunity"]["opportunity_id"])

    # Quantity chain: quoted -> ordered -> shipped -> remaining.
    ordered, shipped = order_line["ordered_quantity"], order_line["shipped_quantity"]
    remaining = remaining_order_quantity(ordered, shipped)
    expect("remaining_order_quantity", order_line["remaining_order_quantity"], remaining)
    expect("converted_quantity", quote_line["converted_quantity"]["value"], ordered)
    expect(
        "unconverted_quantity",
        quote_line["unconverted_quantity"]["value"],
        quote_line["quoted_quantity"] - ordered,
    )
    expect("opportunity won amount", Decimal(str(data["opportunity"]["closed_won_amount"]["value"])),
           Decimal(str(order_line["ordered_amount"])))
    expect("quote reserves no stock", quote_line["reserves_stock"], False)

    # Shipments and invoices cannot exceed what the order line says.
    shipment_total = sum(
        line["shipped_quantity"]
        for shipment in data["shipments"]
        for line in shipment["lines"]
        if line["order_line_id"] == order_line["order_line_id"]
    )
    expect("sum of shipment lines", shipment_total, shipped)
    invoiced = sum(l["invoiced_quantity"] for inv in data["invoices"] for l in inv["lines"])
    if invoiced > shipped:
        problems.append(f"invoiced quantity {invoiced} exceeds shipped quantity {shipped}")
    expect(
        "delivery confirmed quantity <= shipped",
        data["shipments"][0]["delivery_confirmed_quantity"] <= data["shipments"][0]["lines"][0]["shipped_quantity"],
        True,
    )

    # Inventory: a reservation is part of on-hand, not extra demand.
    inv = data["inventory"]
    last = inv["stock_history"][-1]
    snap = inv["at_snapshot"]
    expect("snapshot on_hand matches history", snap["on_hand"], last["on_hand"])
    expect("snapshot reserved matches history", snap["reserved"], last["reserved"])
    for point in inv["stock_history"] + [snap]:
        expect("available_to_promise = on_hand - reserved", point["available_to_promise"],
               point["on_hand"] - point["reserved"])
        if point["reserved"] > point["on_hand"]:
            problems.append(f"reserved exceeds on_hand at {point.get('at', 'snapshot')}")
    open_reserved = sum(r["reserved_quantity"] for r in data["reservations"] if r["status"] == "active")
    expect("open reservations", open_reserved, snap["reserved"])

    # Reporting must not count the quote and the order it became as two demands.
    committed = sum(r["quantity"] for r in data["demand_signals"]["rows"] if r["counts_toward_committed_demand"])
    expect("committed demand rows", committed, data["demand_signals"]["committed_demand_units"])
    expect("committed demand equals ordered quantity", committed, ordered)

    summary = data["quantity_summary_at_snapshot"]
    expect("summary quoted", summary["quoted_quantity"], quote_line["quoted_quantity"])
    expect("summary ordered", summary["ordered_quantity"], ordered)
    expect("summary shipped", summary["shipped_quantity"], shipped)
    expect("summary remaining", summary["remaining_order_quantity"], remaining)
    expect("summary unconverted", summary["unconverted_quote_quantity"], quote_line["quoted_quantity"] - ordered)
    expect("summary on_hand", summary["on_hand_quantity"], snap["on_hand"])
    expect("summary reserved", summary["reserved_quantity_open"], snap["reserved"])
    expect("summary inbound", summary["inbound_expected_quantity"], data["inbound_supply"][0]["expected_quantity"])

    # Changed-condition walkthrough: ship the remaining unit without double counting.
    walk = data["changed_condition_walkthrough"]
    after = walk["after"]
    before = dict(
        summary,
        committed_demand_units=data["demand_signals"]["committed_demand_units"],
        order_status=order["status"],
    )
    expect("walkthrough ships exactly the remaining units", after["shipped_quantity"] - shipped, remaining)
    expect("walkthrough remaining after", after["remaining_order_quantity"],
           remaining_order_quantity(after["ordered_quantity"], after["shipped_quantity"]))
    expect("walkthrough on_hand after", after["on_hand_quantity"], walk["events"][-1]["on_hand_after"])
    expect("walkthrough reserved after", after["reserved_quantity_open"], walk["events"][-1]["reserved_after"])
    for key in walk["unchanged"]:
        expect(f"walkthrough unchanged: {key}", after[key], before[key])
    for key in walk["changed"]:
        if after[key] == before[key]:
            problems.append(f"walkthrough lists {key} as changed but it is identical")

    # The first cohort row must be the scenario itself.
    cohort_rows = data["illustrative_cohort"]["rows"]
    expect("cohort row 0 equals scenario", cohort_rows[0], scenario_row(data))
    return problems


def summarize(data):
    """Compute every metric for the scenario alone and for the invented cohort."""
    cohort = data["illustrative_cohort"]
    rows = cohort["rows"]
    single = [scenario_row(data)]
    price = data["product"]["unit_price"]
    # Win rate is by close date within the period: period start to the snapshot, as in docs/business-metrics.md.
    period = {"period_start": cohort["period_start"], "period_end": cohort["snapshot_at"]}
    return {
        "scenario": {
            "remaining_order_quantity": remaining_order_quantity(
                single[0]["ordered_quantity"], single[0]["shipped_quantity"]),
            "quote_to_order_conversion": quote_to_order_conversion(single),
            "order_fill_rate": order_fill_rate(single),
            "backlog": backlog_units(single, price),
            "quotation_turnaround": quotation_turnaround_hours(single),
            "opportunity_win_rate": opportunity_win_rate(single, **period),
        },
        "cohort": {
            "quote_to_order_conversion": quote_to_order_conversion(rows),
            "order_fill_rate": order_fill_rate(rows),
            "backlog": backlog_units(rows),
            "quotation_turnaround": quotation_turnaround_hours(rows),
            "opportunity_win_rate": opportunity_win_rate(rows, **period),
        },
    }


def _fmt(value):
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def main(argv):
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read {path}: {exc}", file=sys.stderr)
        return 1

    try:
        problems = check_scenario(data)
        report = summarize(data)
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        print(f"ERROR: scenario is malformed or inconsistent: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(f"Scenario: {path.name} (fictional; snapshot {data['meta']['snapshot_at']})")
    print("Consistency checks:", "PASS" if not problems else f"FAIL ({len(problems)} problem(s))")
    for problem in problems:
        print(f"  - {problem}")
    for section, metrics in report.items():
        print(f"\n[{section}]")
        for name, value in metrics.items():
            if isinstance(value, dict):
                print(f"  {name}: " + ", ".join(f"{k}={_fmt(v)}" for k, v in value.items()))
            else:
                print(f"  {name}: {_fmt(value)}")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
