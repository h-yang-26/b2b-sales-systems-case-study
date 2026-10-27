# Design Decisions (Hypothetical, Fictional)

Three short architecture decision records (ADRs) for the invented distributor. Each follows Context -> Decision -> Consequences and uses the scenario in [`examples/fictional-order-scenario.json`](../examples/fictional-order-scenario.json): quote 4 units, order 2, ship 1, 1 remaining. These are reasoned choices for a teaching exercise, not decisions made in a real organization.

---

## ADR-001: Reserve stock when an order is accepted, not when a quote is issued

**Status:** Accepted (hypothetical)

**Context.** `QUO-2001` offered 4 units of `LAB-CF-200` on 2026-03-04, valid until 2026-03-18. One unit was on hand. Many quotes are never accepted, and this one converted only 2 of its 4 units. If every quote held stock, the single on-hand unit could sit idle for two weeks for a deal that might not happen, while another customer ready to order could not have it.

**Decision.** A quote does not reserve stock (`reserves_stock: false`). The Quotation module may *look up* availability to give an indication, but only the Orders module, after the customer accepts, asks Inventory and Fulfillment to create a reservation. On 2026-03-10, accepting `SO-3001` triggered `RSV-6001` for the 1 available unit; the second ordered unit could not be reserved and stays as open order quantity.

**Consequences.**

- Stock is available to buyers who commit first, so on-hand is less often tied up by speculative quotes.
- The order for 2 could only be partly reserved. A customer shown "in stock" at quoting time may later learn that only part of an order can ship immediately. The business must set that expectation (for example with the estimated ship date on the order line).
- Quote validity dates become more important, since acceptance within the window is not a guarantee of stock.
- This choice would be reconsidered for scarce, high-value, or made-to-order items, where a time-limited hold on a quote could be worth the idle stock.

---

## ADR-002: The Orders module owns order status; fulfillment facts drive it

**Status:** Accepted (hypothetical)

**Context.** After `SHP-4001` shipped 1 of 2 units, several parties could plausibly say what state `SO-3001` is in: sales (it is won), the warehouse (one shipment is done), or finance (one unit is invoiced). If each edited the status, the order could be shown as "closed", "partially fulfilled", and "won" at once, and reports would disagree.

**Decision.** Orders is the single owner of `SO-3001`'s status and of `shipped_quantity` and `remaining_order_quantity` on its lines. Inventory and Fulfillment owns the shipment and reservation facts and reports each confirmed shipment to Orders. Orders then recomputes `remaining_order_quantity = ordered_quantity - shipped_quantity` (2 - 1 = 1) and sets the status to `partially_fulfilled`; it moves to `fulfilled` only when remaining reaches 0, as in the walkthrough. `remaining_order_quantity` is derived and never hand-edited. CRM's `closed_won` stage is a different fact, about the sale, and does not mean fulfilled.

**Consequences.**

- Every status question has one answer and one place to look.
- One shipment can be linked to an order without claiming the order is fulfilled.
- Orders depends on prompt, correct shipment confirmations. A duplicated confirmation would double-count shipped units, so shipment confirmations need unique identifiers (`SHP-4001`) and a rule that shipped quantity can never exceed ordered quantity.
- A missing estimate (`estimated_ship_date` null) must be shown as "no estimate", not as an immediate ship date.
- Cancellations and returns are not covered; adding them would change the status model and the remaining-quantity formula.

---

## ADR-003: Count committed demand from order lines, and link quotes and opportunities by identifier

**Status:** Accepted (hypothetical)

**Context.** The same customer need appears three times: as `OPP-1001` (expected 7,400.00 USD), as `QL-2001-1` (4 units), and as `OL-3001-1` (2 units). A dashboard that simply added open opportunities, quotes, and orders would report far more demand than the business has committed to, and would count the same units again when they ship.

**Decision.** *Committed demand* is the quantity on accepted order lines: 2 units. Quote lines are reported separately as a *signal* (4 units), never added to orders. Each downstream record keeps the identifier of its source (`OL-3001-1` -> `QL-2001-1` -> `OPP-1001`), and Reporting builds its views from those links, including the `demand_signals` rows in the JSON, where only `OL-3001-1` has `counts_toward_committed_demand: true`. Shipping changes shipped and remaining quantities, not demand: after `SHP-4002` in the walkthrough, committed demand is still 2.

**Consequences.**

- Demand and conversion numbers can be audited back to individual records.
- Conversion and win rate become measurable, because the unconverted 2 units and the lost opportunities stay visible instead of being deleted.
- The design relies on reliable identifiers at every hand-off. A manually created order with no `quote_line_id` would appear as demand with no signal, and would be excluded from conversion unless handled explicitly.
- Opportunity win rate (by count) and quote-to-order conversion (by units) answer different questions and will give different numbers for the same period; see [business-metrics.md](business-metrics.md).
