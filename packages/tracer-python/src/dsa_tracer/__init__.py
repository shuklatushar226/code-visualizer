"""dsa_tracer — produce Trace Event Protocol JSON from Python source."""

from .tracer import trace_source, TraceResult

__all__ = ["trace_source", "TraceResult"]
__version__ = "0.1.0"
