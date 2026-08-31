from __future__ import annotations
from typing import Any, Dict
from .models import CanonicalStudy

def flatten_for_warehouse(study: CanonicalStudy) -> Dict[str, Any]:
    d = study.to_dict(include_raw=False)
    return {
        "nct_id": d["nct_id"], "brief_title": d["brief_title"], "official_title": d["official_title"],
        "overall_status": d["overall_status"], "phase": d["phase"], "study_type": d["study_type"],
        "conditions": d["conditions"], "start_date": d["start_date"],
        "primary_completion_date": d["primary_completion_date"], "completion_date": d["completion_date"],
        "last_update_submit_date": d["last_update_submit_date"], "last_update_post_date": d["last_update_post_date"],
        "has_results": d["has_results"], "enrollment_count": d["enrollment_count"],
        "num_locations": len(d["locations"]), "num_interventions": len(d["interventions"]),
    }
