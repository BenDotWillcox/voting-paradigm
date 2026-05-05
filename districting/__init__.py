"""
Districting domain package.

Algorithmic redistricting demos. Two surfaces:

  - apportionment: how many seats each state gets given a total House size
    (Method of Equal Proportions, the rule in current US law)
  - algorithm:     how to draw districts within a state given its seat count
    (balanced power diagrams; Cohen-Addad / Klein / Young, arXiv 1710.03358)

Step 1 of the build sequence (see prompts/demo-3-districting.md) ships the
apportionment piece only. The districting algorithm itself is step 3.

Boundary rules (per CLAUDE.md):
  - Pure Python; no DB writes, no HTTP, no I/O at import time.
  - May import from voting/ (foundational primitive). Does NOT import from
    preferences/, delegation/, or other demo packages.
"""

from .algorithm import (
    DistrictCenter,
    DistrictingError,
    DistrictingResult,
    Unit,
    balanced_power_diagram,
)
from .apportionment import (
    apportion,
    apportion_us_2020,
    priority_value,
    InvalidApportionmentError,
)
from .data.apportionment_2020 import (
    US_2020_APPORTIONMENT_POPULATIONS,
    US_2020_KNOWN_APPORTIONMENT,
    US_2020_TOTAL_APPORTIONMENT_POPULATION,
)

__all__ = [
    # Apportionment
    "apportion",
    "apportion_us_2020",
    "priority_value",
    "InvalidApportionmentError",
    # Districting algorithm
    "balanced_power_diagram",
    "Unit",
    "DistrictCenter",
    "DistrictingResult",
    "DistrictingError",
    # 2020 reference data
    "US_2020_APPORTIONMENT_POPULATIONS",
    "US_2020_KNOWN_APPORTIONMENT",
    "US_2020_TOTAL_APPORTIONMENT_POPULATION",
]
