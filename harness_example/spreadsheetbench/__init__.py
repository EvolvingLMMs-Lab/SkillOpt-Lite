"""SpreadsheetBench harness_example (standalone runtime copy).

Mirrors :mod:`skillopt.envs.spreadsheetbench` so the harness training loop
can edit ``rollout.py`` / ``react_agent.py`` / ``codegen_agent.py`` in place
without touching the production package.  Absolute imports of
``skillopt.envs.spreadsheetbench.*`` are rewritten as relative imports so
this bundle is self-contained.
"""

from .adapter import SpreadsheetBenchAdapter

__all__ = ["SpreadsheetBenchAdapter"]
