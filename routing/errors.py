"""Domain errors. The views map these onto HTTP status codes."""


class BadRequest(ValueError):
    """The caller's input is invalid (HTTP 400)."""


class InfeasibleRoute(Exception):
    """No fuel plan can cover the route with the given range (HTTP 422)."""


class RoutingUnavailable(Exception):
    """The upstream routing service failed or timed out (HTTP 502)."""


class DataNotBuilt(Exception):
    """stations.json / places.json are missing (HTTP 503)."""
