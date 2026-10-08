"""HTTP API layer: routes, dependencies, and error handling.

Route handlers are intentionally thin — they authenticate, validate input, call
a service, and shape the response. All business logic lives in the service
layer.
"""
