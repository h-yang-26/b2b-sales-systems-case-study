# Business Metrics (Hypothetical, Fictional)

Five B2B metrics with explicit units, populations, time bases, numerators, denominators, and missing-data behavior. All numbers are invented. They come from the scenario in [`examples/fictional-order-scenario.json`](../examples/fictional-order-scenario.json) and its small `illustrative_cohort`, and are reproduced by `python scripts/scenario_calc.py`.

## The invented cohort

Snapshot: 2026-03-20 17:00 UTC. Period: quotes issued from 2026-03-01 to the snapshot. Units are centrifuges. The first row is the main scenario; the other four are invented only to give the denominators something to differ on.

| Quote | Opportunity | Hours requested -> issued | Quote outcome | Quoted units | Ordered units | Shipped units | Opportunity outcome |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `QUO-2001` | `OPP-1001` | 30 | partially_accepted | 4 | 2 (`SO-3001`) | 1 | won |
| `QUO-2002` | `OPP-1002` | 24 | accepted | 3 | 3 (`SO-3002`) | 3 | won |
| `QUO-2003` | `OPP-1003` | 20 | lost | 5 | 0 | 0 | lost |
| `QUO-2004` | `OPP-1004` | request time missing | open | 2 | 0 | 0 | open |
| `QUO-2005` | `OPP-1005` | 30 | lost | 6 | 0 | 0 | lost |

## Summary: five metrics, five different denominators

| Metric | Unit | Population (denominator) | Scenario only (`SO-3001`) | Cohort |
| --- | --- | --- | --- | --- |
| Quote-to-order conversion | % of quoted units | Quoted units on decided quotes | 2 / 4 = 50% | 5 / 18 = 27.8% |
| Order fill rate | % of ordered units | Ordered units on accepted orders | 1 / 2 = 50% | 4 / 5 = 80% |
| Backlog | units (and USD) | Not a ratio: sum of remaining quantity | 1 unit = 1,850.00 USD | 1 unit |
| Quotation turnaround | hours | Quotes with both timestamps | 30 h | median 27 h (mean 26 h), 4 quotes |
| Opportunity win rate | % of opportunities | Opportunities closed in the period | 1 / 1 = 100% | 2 / 4 = 50% |

A single record cannot tell you much (a win rate of 1 / 1 is not meaningful), so the scenario-only column shows the arithmetic and the cohort column shows how the denominators separate. Note that conversion (27.8%) and win rate (50%) differ for the same period because one counts units and the other counts opportunities: `OPP-1001` is a win even though only half of its quoted units were ordered.

---

## 1. Quote-to-order conversion

- **Question:** what share of the quantity we offered, on quotes that have reached an outcome, did customers order?
- **Unit and basis:** percent of units; cohort by quote issue date (quotes issued in the period).
- **Eligible population:** quote lines on quotes issued in the period whose outcome is decided (`accepted`, `partially_accepted`, `lost`). Quotes still `open` are excluded because their outcome is unknown, and the number excluded is reported.
- **Formula:** `sum(ordered units traced to those quote lines) / sum(quoted units on those quote lines)`.
- **Example:** scenario: `2 / 4 = 50%`. Cohort: decided quotes are `QUO-2001`, `QUO-2002`, `QUO-2003`, `QUO-2005`; ordered `2 + 3 + 0 + 0 = 5`; quoted `4 + 3 + 5 + 6 = 18`; `5 / 18 = 27.8%`; 1 open quote (`QUO-2004`, 2 units) excluded.
- **Data required:** quote lines with `quoted_quantity` and outcome; order lines with `quote_line_id`.
- **Missing data:** an order with no `quote_line_id` cannot be traced and is excluded (and should be reported). An empty population gives "not available", never 0%.
- **Not the same as:** shipped units or revenue. An order line counts once, when accepted.

## 2. Order fill rate

- **Question:** of the units customers have ordered, how many have we shipped so far?
- **Unit and basis:** percent of units; snapshot at 2026-03-20 17:00 UTC, cumulative since acceptance.
- **Eligible population:** order lines on orders accepted on or before the snapshot. Quotes, opportunities, and reservations are not in the population.
- **Formula:** `sum(shipped_quantity) / sum(ordered_quantity)` over eligible order lines.
- **Example:** scenario: `1 / 2 = 50%`. Cohort adds `SO-3002` (3 of 3 shipped): `(1 + 3) / (2 + 3) = 4 / 5 = 80%`. After the walkthrough, `SO-3001` is `2 / 2`, so the cohort would be `5 / 5 = 100%`.
- **Data required:** `ordered_quantity` per order line and shipments linked by `order_line_id`.
- **Missing data:** a missing `shipped_quantity` is an error, not zero. Shipped greater than ordered is an error. Cancelled quantity would have to leave the denominator, but cancellations are out of scope in this version.
- **Limitation:** this is cumulative quantity fill, not "on time and in full": it ignores promised dates.

## 3. Backlog (open order quantity)

- **Question:** how many ordered units do we still owe?
- **Unit and basis:** units, optionally valued in USD at order line price; snapshot.
- **Eligible population:** order lines on accepted orders with `remaining_order_quantity > 0`.
- **Formula:** `sum(remaining_order_quantity)` where `remaining_order_quantity = ordered_quantity - shipped_quantity`. Value: remaining units times the order line unit price.
- **Example:** scenario: `2 - 1 = 1` unit; `1 x 1,850.00 = 1,850.00 USD`. Cohort: `SO-3001` owes 1 and `SO-3002` owes 0, so 1 unit (no price in the invented cohort rows, so no value).
- **Data required:** order lines, shipments, and unit price for valuation.
- **Missing data:** a missing price gives units only (value "not available"). Unconverted quote quantity (the other 2 units of `QL-2001-1`) is **not** backlog, since the customer never committed to it.
- **Not the same as:** on-hand stock. Backlog is owed to customers; on-hand is in the warehouse. Here backlog is 1 while on-hand is 0.

## 4. Quotation turnaround time

- **Question:** how long does it take to answer a quote request?
- **Unit and basis:** hours between `quote_requested_at` and the first `issued_at`; cohort by issue date, UTC timestamps, elapsed (not business) hours.
- **Eligible population:** quotes issued in the period that have both timestamps.
- **Formula:** median of `issued_at - quote_requested_at`, with the mean shown for comparison; the median is less distorted by one very slow quote.
- **Example:** scenario: 2026-03-03 09:00 -> 2026-03-04 15:00 = 30 h. Cohort: `30, 24, 20, 30` for `QUO-2001`, `QUO-2002`, `QUO-2003`, `QUO-2005`; sorted `20, 24, 30, 30`; median `(24 + 30) / 2 = 27 h`, mean `104 / 4 = 26 h`. `QUO-2004` has no request time and is excluded and counted (1).
- **Data required:** request timestamp and first issue timestamp on every quote.
- **Missing data:** a missing request time is excluded, never treated as 0 hours. An issue time before the request time is an error.
- **Limitation:** revised quote versions do not restart the clock; only the first issue counts.

## 5. Opportunity win rate

- **Question:** of the opportunities that were decided, how many did we win?
- **Unit and basis:** percent of opportunities (a count, regardless of size); cohort by close date within the period. The period here is the same window as above: from 2026-03-01 00:00 UTC to the snapshot, inclusive at both ends.
- **Counting unit:** each distinct `opportunity_id` counts once. An opportunity may have several quotes ([data-model.md](data-model.md)), so quote rows are never counted. If the rows for one opportunity disagree on outcome or close date, that is a data error and is reported as one rather than resolved by picking a row.
- **Input errors:** an opportunity identifier must be non-blank text. A period whose start is after its end is an error, not an empty population.
- **Eligible population:** distinct opportunities with outcome `won` or `lost` and a close date in the period. `open` opportunities are excluded and reported.
- **Formula:** `closed_won / (closed_won + closed_lost)`.
- **Example:** scenario: `1 / 1 = 100%` (illustrative only). Cohort: won `OPP-1001`, `OPP-1002`; lost `OPP-1003`, `OPP-1005`; `2 / 4 = 50%`; `OPP-1004` is open and excluded.
- **Data required:** opportunity outcome and close timestamp.
- **Missing data:** a closed opportunity with no close date is excluded and reported (by count and identifier); so is one closed outside the period. An empty population gives "not available". Example: if `OPP-1002` had no close date, the cohort would be `1 / 3` (`OPP-1001` won; `OPP-1003` and `OPP-1005` lost) with 1 exclusion reported, not `2 / 4`.
- **Limitation:** a count-based rate treats a 2-unit win and a 20-unit loss alike. A value-weighted version would be a separate metric with its own denominator.

---

## Why the denominators differ

| Metric | Denominator is | Why not another |
| --- | --- | --- |
| Conversion | quoted units on decided quotes | measures how much of an offer became commitment |
| Fill rate | ordered units on accepted orders | measures delivery against commitment; quotes are irrelevant here |
| Backlog | none (a sum) | what is owed now |
| Turnaround | quotes with both timestamps | response speed, independent of outcome |
| Win rate | closed opportunities | whether a sales pursuit succeeded, regardless of quantity |

Using, for instance, quoted units as the denominator of fill rate would make `SO-3001` look 1 / 4 = 25% filled, mixing an offer with a commitment. Using "all opportunities including open" for win rate would count undecided deals as failures.

## What the example calculator enforces

[`scripts/scenario_calc.py`](../scripts/scenario_calc.py) is a small checking aid, not a reporting system, and it does not implement every rule written above.

- **Enforced and tested:** the win-rate population rule in section 5 (distinct opportunities, close date within the period, exclusion and reporting of open, missing-close-date, and out-of-period records, an error on conflicting rows or an unknown outcome); remaining quantity, with an error on missing, negative, or over-shipped quantities; exclusion of open quotes from conversion; exclusion and counting of missing request times in turnaround; empty populations giving "not available" rather than 0.
- **Not enforced:** the calculator takes the cohort rows it is given as already filtered. It does not apply the quote-issue-date period to conversion and turnaround, the acceptance-date cut-off to fill rate, or the exclusion of orders with no `quote_line_id` from conversion. Applying those would need more fields in the example than it carries.

## Data requirements and limits

- Every record must carry the identifier of its source (`quote_line_id` on order lines, `order_line_id` on shipments); see [data-model.md](data-model.md).
- All timestamps are UTC ISO 8601; the snapshot time is part of each metric's definition.
- Cancellations and returns are excluded in this version, so fill rate and backlog would need revision once they exist.
- The numbers are invented illustrations of arithmetic and denominators. They are not benchmarks and not real business results.
