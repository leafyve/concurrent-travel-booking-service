"""Service layer — the home of business rules and transaction boundaries.

Route handlers stay thin: they authenticate, parse input, and delegate here.
Services orchestrate repositories, enforce invariants, own the transaction, and
write outbox events in the *same* transaction as the state change.
"""
