"""Runtime policy separating automatically certifiable and higher-risk semantic strata.

PRIMARY/BLIND role certification currently has governed acceptance thresholds only
for W2/S1. W3 and S2/S3 material must not inherit that authority. Instead it must
remain explicitly routed to a bounded review surface. This module makes that
boundary deterministic and testable.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

AUTO_CERT_WORK_CLASS = "W2"
AUTO_CERT_SOURCE_CLASS = "S1"
LOCAL_COMPLETE = "LOCAL_PRECISION_COMPLETE"


def is_automatic_certification_stratum(risk: dict[str, Any]) -> bool:
    return (
        str(risk.get("work_class") or "") == AUTO_CERT_WORK_CLASS
        and str(risk.get("source_class") or "") == AUTO_CERT_SOURCE_CLASS
    )


def partition_certification_strata(risks: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    eligible = sorted(uid for uid, risk in risks.items() if is_automatic_certification_stratum(risk))
    higher = sorted(set(risks) - set(eligible))
    return {
        "automatic_certification_units": eligible,
        "higher_risk_review_units": higher,
    }


def assess_higher_risk_routing(risks: dict[str, dict[str, Any]], routes: list[dict[str, Any]]) -> dict[str, Any]:
    strata = partition_certification_strata(risks)
    higher = set(strata["higher_risk_review_units"])
    by_unit: dict[str, list[dict[str, Any]]] = defaultdict(list)
    malformed_routes: list[int] = []
    for idx, route in enumerate(routes):
        uid = route.get("source_unit_id")
        if not isinstance(uid, str) or not uid:
            malformed_routes.append(idx)
            continue
        by_unit[uid].append(route)

    missing = sorted(uid for uid in higher if not by_unit.get(uid))
    local_complete = sorted(
        uid for uid in higher
        if any(str(row.get("action") or "") == LOCAL_COMPLETE for row in by_unit.get(uid, []))
    )
    bounded = sorted(
        uid for uid in higher
        if by_unit.get(uid) and all(str(row.get("action") or "") != LOCAL_COMPLETE for row in by_unit[uid])
    )
    controlled = not missing and not local_complete and not malformed_routes
    return {
        **strata,
        "bounded_higher_risk_units": bounded,
        "missing_route_units": missing,
        "higher_risk_units_with_local_complete_route": local_complete,
        "malformed_route_indexes": malformed_routes,
        "higher_risk_routing_controlled": controlled,
    }
