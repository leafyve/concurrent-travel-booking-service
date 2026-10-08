"""Pydantic v2 request/response schemas (the API's public contract).

ORM models are never returned directly; services map them into these DTOs so the
wire format is decoupled from the database layout.
"""
