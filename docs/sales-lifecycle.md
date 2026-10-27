# Sales Lifecycle (Hypothetical, Fictional)

This is a design-exercise narrative for an invented distributor, Northgate Lab Supply, that sells a non-branded benchtop centrifuge (`LAB-CF-200`). It describes common B2B practice in general terms. It is not a description of any real company's process. All identifiers, dates, prices, and quantities come from [`examples/fictional-order-scenario.json`](../examples/fictional-order-scenario.json).

## The idea in plain language

In B2B sales, "how much did the customer want?" has several different answers depending on the moment you ask:

- what they **asked about** (an opportunity and its quote),
- what they **committed to buy** (an order),
- what we **set aside for them** (a reservation),
- what we **actually sent** (a shipment), and
- what is **still owed** (the remaining order quantity).

Software boundaries make sense when each of these facts has one clear owner. Treating them as one number is how demand gets counted twice.

## Stages

| Stage | Question it answers | Record (this scenario) | Quantity at this stage |
| --- | --- | --- | --- |
| Lead | Is someone possibly interested? | `LEAD-0001`, a website enquiry on 2026-03-02 | none yet |
| Opportunity | Is there a real, qualified chance to sell? | `OPP-1001` for `ACC-001`, created 2026-03-03 | expected value estimated at 7,400.00 USD |
| Quote | What did we offer, at what price, until when? | `QUO-2001` line `QL-2001-1`, issued 2026-03-04, valid to 2026-03-18 | **4 units quoted** |
| Order | What did the customer firmly commit to? | `SO-3001` line `OL-3001-1`, accepted 2026-03-10 | **2 units ordered** (committed demand) |
| Fulfillment | What was set aside, and what physically left? | `RSV-6001` (1 unit reserved), `SHP-4001` (1 unit shipped 2026-03-13) | **1 unit shipped** |
| Invoice and payment (optional) | What did we bill, and has it been paid? | `INV-7001` for 1 unit, 1,850.00 USD, unpaid at the snapshot | 1 unit invoiced |
| Service (optional) | Does the customer need support for what they received? | No record in this version | none |

At the snapshot (2026-03-20 17:00 UTC): quoted 4, ordered 2, shipped 1, remaining 1, with 2 quoted units that never became an order.

## Narrative

1. **Lead to opportunity.** Harbor Valley Testing Co. (fictional) submits an enquiry. Sales qualifies it and creates `OPP-1001`. A lead is interest; it carries no quantity commitment.
2. **Quote.** The customer asks for a price on 4 units. Quotation issues `QUO-2001` with one line for 4 units at 1,850.00 USD (7,400.00 USD). The quote is an *offer* and a *demand signal*. It does not reserve stock in this example (see [ADR-001](design-decisions.md)).
3. **Order.** On 2026-03-10 the customer accepts for **2** units. Orders creates `SO-3001`, linked back to `QUO-2001` and `OPP-1001`. Only now is there committed demand: 2 units. The other 2 quoted units are not extra demand; they are a quote that was not converted.
4. **Reservation.** One unit was on hand, so Inventory and Fulfillment creates `RSV-6001` for 1 unit against `OL-3001-1`. The reservation allocates existing stock. It is not an additional sale and it does not change the ordered quantity.
5. **Shipment.** `SHP-4001` ships that 1 unit on 2026-03-13. The customer confirms delivery on 2026-03-17 (observed). The order is linked to a shipment but is **not** fulfilled: order status is `partially_fulfilled`.
6. **Open quantity.** `remaining_order_quantity = ordered_quantity - shipped_quantity = 2 - 1 = 1`. On hand is 0, so the order waits for inbound purchase order `PO-5001` (2 units). Its expected receipt date, 2026-03-27, is an *estimate*, and the resulting ship estimate of 2026-03-30 is too.
7. **Invoice (optional).** `INV-7001` bills the shipped unit only: 1,850.00 USD, not the 3,700.00 USD order value.
8. **Service (optional).** After delivery the customer might open a support case or request a warranty repair. This version records none.

## Optional branches

These are real in practice and deliberately left out of the first version, which excludes cancellations and returns:

- the customer declines or lets the quote expire (the opportunity becomes lost, no order exists),
- the quote is revised (a new version supersedes the old one),
- the customer orders more than was quoted, or from several quotes at once,
- the order is cancelled or reduced before shipment,
- goods are returned or replaced after delivery,
- a shipment is split across several parcels, or one parcel serves several orders.

Because cancellations and returns are excluded, `remaining_order_quantity = ordered_quantity - shipped_quantity` is a valid first-version formula. Once cancellations exist it would have to subtract cancelled quantity too.

## Terminology differs between companies

"Opportunity", "deal", and "pipeline item" are often the same idea. "Sales order", "customer order", and "booking" overlap. "Available stock" may or may not already net out reservations. This exercise fixes one vocabulary (defined in [data-model.md](data-model.md)) and uses it consistently; a real organization would first agree on its own.

## Continue reading

- Entities and states: [data-model.md](data-model.md)
- Diagrams and ownership: [system-architecture.md](system-architecture.md)
- Metric formulas: [business-metrics.md](business-metrics.md)
