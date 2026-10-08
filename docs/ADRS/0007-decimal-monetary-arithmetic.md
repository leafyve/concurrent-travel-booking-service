# ADR 0007 — Decimal monetary arithmetic with per-currency minor units

**Status:** Accepted · **Context:** independent portfolio project (not Klook).

## Context
Money must be exact. Binary floating point (`float`) cannot represent values like
`0.10` precisely and accumulates error — unacceptable for prices, totals, and
refunds.

## Decision
Represent all money as **`decimal.Decimal`** in Python and **`NUMERIC(12,2)`** in
PostgreSQL. Quantize to a currency's **minor units** (SGD/THB/USD → 2 places;
JPY/KRW → 0 places) with half-up rounding. Payment amounts are matched in
**integer minor units** (as real providers send them).

## Consequences
- No floating-point drift; totals equal `unit_price × quantity` exactly (property-
  tested with Hypothesis).
- Currency-aware rounding handles zero-decimal currencies (e.g. JPY 9800) as well
  as two-decimal ones (e.g. SGD 68.00).
- Webhook amount validation compares integers, avoiding any float comparison.

## Alternatives considered
- **`float`:** rejected — imprecise, unsafe for money.
- **Integer minor units everywhere in the DB:** valid and used *at the payment
  boundary*, but `NUMERIC` columns keep the domain model readable while remaining
  exact.
