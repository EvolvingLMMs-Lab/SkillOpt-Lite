"""SpreadsheetBench environment adapter (harness_example copy).

Mirrors ``skillopt.envs.spreadsheetbench`` so the harness-opt closed loop
can edit ``rollout.py`` / ``react_agent.py`` / ``codegen_agent.py`` etc.
in-place without touching the production package.
"""

from .adapter import SpreadsheetBenchAdapter

__all__ = ["SpreadsheetBenchAdapter"]
