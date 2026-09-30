"""
Apportionment domain package (demo 4).

How many House seats each state receives for a given House size, under the
Method of Equal Proportions (Huntington-Hill), the rule in US law since 1941.

Boundary rules (per CLAUDE.md):
  - Pure Python; no DB writes, no HTTP, no I/O at import time.
  - A foundational primitive, like voting/: other demo packages (districting
    needs seat counts per state) may import it. It imports no demo package.
"""

from .data.apportionment_2020 import (
    US_2020_APPORTIONMENT_POPULATIONS,
    US_2020_KNOWN_APPORTIONMENT,
    US_2020_TOTAL_APPORTIONMENT_POPULATION,
)
from .methods import (
    InvalidApportionmentError,
    apportion,
    apportion_us_2020,
    priority_value,
)

__all__ = [
    "apportion",
    "apportion_us_2020",
    "priority_value",
    "InvalidApportionmentError",
    "US_2020_APPORTIONMENT_POPULATIONS",
    "US_2020_KNOWN_APPORTIONMENT",
    "US_2020_TOTAL_APPORTIONMENT_POPULATION",
]
