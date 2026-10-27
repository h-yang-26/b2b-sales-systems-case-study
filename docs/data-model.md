# Data Model and Glossary (Hypothetical, Fictional)

A deliberately small domain model for the invented distributor in [sales-lifecycle.md](sales-lifecycle.md). Identifiers, states, and numbers match [`examples/fictional-order-scenario.json`](../examples/fictional-order-scenario.json). It is a teaching model, not a production schema: no keys, indexes, permissions, or price catalogs are defined.

## Reading guide

- **Identifier** says how a record is named. **Owner** is the logical module responsible for the truth of that record (see [system-architecture.md](system-architecture.md)); it does not imply a separate service or database.
- Values are tagged in the JSON as **observed** (something that happened), **estimated** (a prediction), **derived** (computed from other fields), or **missing** (`null`, unknown). These are never interchangeable.

## Entities

| Entity | Identifier (example) | Owner | Relationships | Key states |
| --- | --- | --- | --- | --- |
| Account | `ACC-001` | CRM | has many Leads, Opportunities, Orders, Invoices | active |
| Lead | `LEAD-0001` | CRM | may become one Opportunity | new, converted_to_opportunity, disqualified |
| Opportunity | `OPP-1001` | CRM | belongs to an Account; has one or more Quotes; may result in Orders | open, closed_won, closed_lost |
| Quote and QuoteLine | `QUO-2001`, `QL-2001-1` | Quotation | belongs to one Opportunity; each line asks for a quantity of a SKU at a price | draft, issued (reported as outcome `open`), accepted, partially_accepted, lost (declined or expired) |
| SalesOrder and OrderLine | `SO-3001`, `OL-3001-1` | Orders | refers to the Quote, QuoteLine, and Opportunity it came from; each line has an ordered quantity | accepted, partially_fulfilled, fulfilled |
| Inventory | SKU `LAB-CF-200` at `WH-MAIN` | Inventory and Fulfillment | holds on-hand quantity; receives inbound supply (`PO-5001`) | quantities only: on_hand, reserved, available_to_promise |
| Reservation | `RSV-6001` | Inventory and Fulfillment | allocates stock to exactly one OrderLine | active, consumed_by_shipment, released |
| Shipment | `SHP-4001` | Inventory and Fulfillment | ships quantities against one or more OrderLines | shipped, delivery confirmed |
| Invoice (optional) | `INV-7001` | Billing (optional, outside the five modules) | bills shipped quantities of one Order | issued; payment unpaid or paid |

Order, quote, and opportunity identifiers form a lineage: `OPP-1001` -> `QUO-2001` / `QL-2001-1` -> `SO-3001` / `OL-3001-1` -> `RSV-6001`, `SHP-4001`, `INV-7001`. Every downstream record stores the identifier of the record it came from. That link is what lets reporting follow one customer need through the whole flow without counting it again.

## Quantity vocabulary

All quantities are in units (one centrifuge). Values below are at the snapshot, 2026-03-20 17:00 UTC.

| Term | Meaning | Where it lives | Value |
| --- | --- | --- | --- |
| `quoted_quantity` | Units offered on a quote line | QuoteLine | 4 |
| `converted_quantity` | Quoted units that became an order line (derived) | QuoteLine | 2 |
| `unconverted_quote_quantity` | `quoted_quantity - converted_quantity` (derived); not demand | QuoteLine | 2 |
| `ordered_quantity` | Units the customer firmly committed to | OrderLine | 2 |
| `shipped_quantity` | Units physically sent, summed over shipments | OrderLine (from Shipments) | 1 |
| `remaining_order_quantity` | `ordered_quantity - shipped_quantity` (derived); also called "open order quantity" in prose | OrderLine | 1 |
| `on_hand` | Physical units in the warehouse, including reserved ones | Inventory | 0 |
| `reserved` | Units on hand that are set aside for specific order lines | Inventory / Reservation | 0 |
| `available_to_promise` | `on_hand - reserved` (derived): what could be committed to someone else now | Inventory | 0 |
| `inbound_expected_quantity` | Units on a purchase order not yet received (estimated arrival) | Inbound supply | 2 |

`remaining_order_quantity` is an *order* concept (what is owed). `on_hand` is a *warehouse* concept (what is physically here). They happen to differ in this scenario: 1 unit is owed while 0 units are on hand, so the order must wait.

## Committed demand

**Committed demand** is the quantity on accepted order lines: here, 2 units from `OL-3001-1`.

- A quote is an offer and a demand *signal*. Its 4 units are not committed demand.
- When 2 of those units become an order, they are **not added** to the quote: the quote signal and the order line describe the same customer need at different stages. Reports count the order line (2) as committed demand and may show the quote line (4) as a separate signal. They never sum them (that would give 6).
- The 2 unconverted units remain visible as a signal, which is what makes conversion measurable, but they are not demand the business has promised to serve.
- A reservation is not additional demand. It is an allocation of 1 existing on-hand unit to the 2-unit order line.

## Why a quote is not a stock reservation (in this example)

In this example, a quote does not hold stock by default (`reserves_stock: false` in the JSON):

- Quotes are cheap to issue and many are never accepted. Here only 2 of 4 units converted, and the cohort in [business-metrics.md](business-metrics.md) shows 5 of 18 decided quoted units converting. Holding stock for each would leave it unavailable to buyers who are ready to order.
- A quote has a validity window (here to 2026-03-18) and the customer may take only part of it.
- The business can still show indicative availability on a quote without reserving anything.

The consequence is that stock seen at quoting time may be gone when the customer accepts; see [ADR-001](design-decisions.md). A distributor with scarce, high-value, or made-to-order goods might reasonably decide differently.

## Estimated, observed, and missing values

| Concept | Estimated (prediction) | Observed (fact) | Missing |
| --- | --- | --- | --- |
| Inbound supply | `expected_receipt_date` 2026-03-27 on `PO-5001` | `actual_receipt_date` (null until received) | `null` expected date with `eta_status` "unknown" |
| Order line ship date | `estimated_ship_date` 2026-03-30 | `shipped_at` of `SHP-4001`: 2026-03-13 | `null`: no estimate yet |
| Delivery | `estimated_delivery_date` 2026-03-17 | `delivery_confirmed_at` 2026-03-17T10:20 | `null`: not yet confirmed |

Two distinctions matter:

- An **estimate is not a fact**. When `PO-5001` actually arrives, the observed date replaces the estimate (the walkthrough below receives it three days late); it does not "confirm" it.
- A **missing ETA is not a zero-day ETA**. `null` means "we do not know when"; a lead time of 0 days means "available now". Treating missing as zero would promise stock that does not exist. Metrics exclude and count missing values rather than treating them as zero.

## Changed-condition walkthrough: the remaining unit ships

Hypothetical continuation of the snapshot, taken from `changed_condition_walkthrough` in the JSON:

1. 2026-03-30: `PO-5001` is received (observed). On hand goes 0 -> 2.
2. 2026-03-30: `RSV-6002` reserves 1 unit for `OL-3001-1`. Reserved goes 0 -> 1; `available_to_promise` is 1.
3. 2026-03-31: `SHP-4002` ships that unit. `RSV-6002` is consumed, reserved goes 1 -> 0, on hand goes 2 -> 1.
4. 2026-04-01: `INV-7002` bills the second unit (optional).

| Quantity or state | Before | After | Changed? |
| --- | --- | --- | --- |
| `quoted_quantity` | 4 | 4 | no |
| `ordered_quantity` | 2 | 2 | no |
| `unconverted_quote_quantity` | 2 | 2 | no |
| Committed demand | 2 | 2 | no (the order is not counted again) |
| `shipped_quantity` | 1 | 2 | yes |
| `remaining_order_quantity` | 1 | 0 | yes |
| Order status | `partially_fulfilled` | `fulfilled` | yes |
| `on_hand` | 0 | 1 | yes (the extra unit from `PO-5001` is free stock, unrelated to this order) |
| `reserved` | 0 | 0 | no net change after consumption |

Shipping does not create a new order or new demand; it moves quantity from "owed" to "shipped".

## Limitations of this model

- Cancellations, returns, substitutions, and amended orders are excluded.
- One SKU, one warehouse, one price, one currency. No tax, discount, or allocation among competing orders.
- Quote revisions beyond `version: 1` are not modeled.
- States are illustrative; a real business would define its own and who may change them.
