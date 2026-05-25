"""cpp_tracer — C++ tracer for DSA Code Visualizer.

Compiles user C++ source with -g -O0 and steps it under GDB/MI to emit
Trace Event Protocol JSON. Annotated structs (via ``viz.hpp`` macros)
get a structured representation; everything else falls back to a
generic object view.
"""
__version__ = "0.1.0"

from .cpp_tracer import trace_source

__all__ = ["trace_source"]
