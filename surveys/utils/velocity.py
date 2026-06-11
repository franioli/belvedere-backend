"""Point velocity computation between consecutive surveys.

Replicates the semantics of the legacy `points_movement_filtered` Postgres
view: consecutive measurement pairs of a point are kept only when the time
gap is a "yearly" one (280 < dt < 400 days) and the displacement is non-zero.
"""

import math
from typing import Any

from surveys.models import Measurement

DT_MIN_DAYS = 280
DT_MAX_DAYS = 400


def compute_point_velocities(measurements: list[Measurement]) -> list[dict[str, Any]]:
    """Compute yearly velocities from measurements ordered by survey date.

    Args:
        measurements: Measurements of a single point, ordered by survey date,
            with the related survey preloaded.

    Returns:
        One record per valid consecutive pair:
        ``{"survey_year": int, "survey_date_fin": date, "v": float}`` (m/day).
    """
    records: list[dict[str, Any]] = []
    for prev, curr in zip(measurements, measurements[1:], strict=False):
        if prev.survey.date is None or curr.survey.date is None:
            continue
        dt = (curr.survey.date - prev.survey.date).days
        if not (DT_MIN_DAYS < dt < DT_MAX_DAYS):
            continue
        d = math.sqrt(
            (curr.east - prev.east) ** 2
            + (curr.north - prev.north) ** 2
            + (curr.h - prev.h) ** 2
        )
        if d <= 0:
            continue
        records.append(
            {
                "survey_year": curr.survey.year,
                "survey_date_fin": curr.survey.date,
                "v": d / dt,
            }
        )
    return records
