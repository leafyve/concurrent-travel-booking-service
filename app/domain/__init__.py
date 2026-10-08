"""Domain layer: pure business rules with no framework or I/O dependencies.

Everything here is deterministic and unit-testable in isolation: status enums,
money arithmetic, cancellation policies, request fingerprinting, and the typed
error hierarchy that the API translates into RFC 7807 responses.
"""
