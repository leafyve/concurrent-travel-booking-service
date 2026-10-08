"""Repository layer.

Thin, purpose-built persistence helpers over the async SQLAlchemy session. Each
repository owns the queries for one aggregate and hides SQL/locking details from
the services. No business rules live here.
"""
