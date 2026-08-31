"""Lossless analytical projection of the ClinicalTrials.gov v2 study record.

The model exposes high-value fields for analytics while retaining the complete
protocol/results/annotation/document/derived sections so schema evolution can be
reparsed without another network extraction.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

CANONICAL_SCHEMA_VERSION = "ctg-study-3.0"


@dataclass
class CanonicalStudy:
    nct_id: str
    brief_title: str
    official_title: Optional[str] = None
    acronym: Optional[str] = None
    nct_id_aliases: List[str] = field(default_factory=list)
    org_study_id_info: Dict[str, Any] = field(default_factory=dict)
    secondary_id_infos: List[Dict[str, Any]] = field(default_factory=list)
    organization: Dict[str, Any] = field(default_factory=dict)

    brief_summary: Optional[str] = None
    detailed_description: Optional[str] = None
    overall_status: Optional[str] = None
    why_stopped: Optional[str] = None
    expanded_access_info: Dict[str, Any] = field(default_factory=dict)

    phase: List[str] = field(default_factory=list)
    study_type: Optional[str] = None
    design: Dict[str, Any] = field(default_factory=dict)
    enrollment_count: Optional[int] = None
    enrollment_type: Optional[str] = None

    conditions: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    sponsors: Dict[str, Any] = field(default_factory=dict)

    start_date: Optional[str] = None
    start_date_type: Optional[str] = None
    primary_completion_date: Optional[str] = None
    primary_completion_date_type: Optional[str] = None
    completion_date: Optional[str] = None
    completion_date_type: Optional[str] = None
    study_first_submit_date: Optional[str] = None
    study_first_post_date: Optional[str] = None
    last_update_submit_date: Optional[str] = None
    last_update_post_date: Optional[str] = None
    last_update_post_date_type: Optional[str] = None

    eligibility_criteria: Optional[str] = None
    minimum_age: Optional[str] = None
    maximum_age: Optional[str] = None
    sex: Optional[str] = None
    gender_based: Optional[bool] = None
    gender_description: Optional[str] = None
    healthy_volunteers: Optional[bool] = None
    standard_ages: List[str] = field(default_factory=list)
    eligibility: Dict[str, Any] = field(default_factory=dict)

    arms: List[Dict[str, Any]] = field(default_factory=list)
    interventions: List[Dict[str, Any]] = field(default_factory=list)
    central_contacts: List[Dict[str, Any]] = field(default_factory=list)
    overall_officials: List[Dict[str, Any]] = field(default_factory=list)
    locations: List[Dict[str, Any]] = field(default_factory=list)

    primary_outcomes: List[Dict[str, Any]] = field(default_factory=list)
    secondary_outcomes: List[Dict[str, Any]] = field(default_factory=list)
    other_outcomes: List[Dict[str, Any]] = field(default_factory=list)

    references: List[Dict[str, Any]] = field(default_factory=list)
    see_also_links: List[Dict[str, Any]] = field(default_factory=list)
    available_ipds: List[Dict[str, Any]] = field(default_factory=list)
    ipd_sharing: Dict[str, Any] = field(default_factory=dict)

    oversight: Dict[str, Any] = field(default_factory=dict)
    has_results: Optional[bool] = None
    is_fda_regulated_drug: Optional[bool] = None
    is_fda_regulated_device: Optional[bool] = None

    # Lossless source sections. These are intentionally preserved even where a
    # field is also projected above.
    protocol_section: Dict[str, Any] = field(default_factory=dict)
    results_section: Dict[str, Any] = field(default_factory=dict)
    annotation_section: Dict[str, Any] = field(default_factory=dict)
    document_section: Dict[str, Any] = field(default_factory=dict)
    derived_section: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self, include_raw: bool = True) -> Dict[str, Any]:
        data = asdict(self)
        if not include_raw:
            for key in ("protocol_section", "results_section", "annotation_section", "document_section", "derived_section"):
                data.pop(key, None)
        return data


def _date_struct(module: Dict[str, Any], key: str) -> Optional[str]:
    value = module.get(key)
    if isinstance(value, dict):
        return value.get("date")
    return value if isinstance(value, str) else None


def _date_type(module: Dict[str, Any], key: str) -> Optional[str]:
    value = module.get(key)
    return value.get("type") if isinstance(value, dict) else None


def _list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def parse_study(raw: Dict[str, Any]) -> CanonicalStudy:
    if not isinstance(raw, dict):
        raise ValueError("study must be a JSON object")

    protocol = raw.get("protocolSection") or {}
    if not isinstance(protocol, dict):
        raise ValueError("protocolSection must be an object")
    ident = protocol.get("identificationModule") or {}
    status = protocol.get("statusModule") or {}
    sponsors_mod = protocol.get("sponsorCollaboratorsModule") or {}
    design = protocol.get("designModule") or {}
    description = protocol.get("descriptionModule") or {}
    conditions_mod = protocol.get("conditionsModule") or {}
    arms = protocol.get("armsInterventionsModule") or {}
    eligibility = protocol.get("eligibilityModule") or {}
    contacts = protocol.get("contactsLocationsModule") or {}
    outcomes = protocol.get("outcomesModule") or {}
    oversight = protocol.get("oversightModule") or {}
    references = protocol.get("referencesModule") or {}
    ipd = protocol.get("ipdSharingStatementModule") or {}

    nct_id = (ident.get("nctId") or raw.get("nctId") or "").strip()
    if not nct_id:
        raise ValueError("study missing NCTId")
    if not nct_id.startswith("NCT"):
        raise ValueError(f"invalid NCTId: {nct_id}")

    phases = [str(p).upper() for p in _list(design.get("phases")) if p]
    conditions = [str(x) for x in _list(conditions_mod.get("conditions")) if x]
    keywords = [str(x) for x in _list(conditions_mod.get("keywords")) if x]

    lead = sponsors_mod.get("leadSponsor") or {}
    collaborators = _list(sponsors_mod.get("collaborators"))
    enrollment = design.get("enrollmentInfo") or {}

    interventions: List[Dict[str, Any]] = []
    for iv in _list(arms.get("interventions")):
        if not isinstance(iv, dict):
            continue
        interventions.append(dict(iv))

    arm_groups = [dict(x) for x in _list(arms.get("armGroups")) if isinstance(x, dict)]
    locations = [dict(x) for x in _list(contacts.get("locations")) if isinstance(x, dict)]
    central_contacts = [dict(x) for x in _list(contacts.get("centralContacts")) if isinstance(x, dict)]
    overall_officials = [dict(x) for x in _list(contacts.get("overallOfficials")) if isinstance(x, dict)]

    has_results = raw["hasResults"] if "hasResults" in raw else None

    return CanonicalStudy(
        nct_id=nct_id,
        brief_title=ident.get("briefTitle") or "",
        official_title=ident.get("officialTitle"),
        acronym=ident.get("acronym"),
        nct_id_aliases=[str(x) for x in _list(ident.get("nctIdAliases")) if x],
        org_study_id_info=dict(ident.get("orgStudyIdInfo") or {}),
        secondary_id_infos=[dict(x) for x in _list(ident.get("secondaryIdInfos")) if isinstance(x, dict)],
        organization=dict(ident.get("organization") or {}),
        brief_summary=description.get("briefSummary"),
        detailed_description=description.get("detailedDescription"),
        overall_status=status.get("overallStatus"),
        why_stopped=status.get("whyStopped"),
        expanded_access_info=dict(status.get("expandedAccessInfo") or {}),
        phase=phases,
        study_type=design.get("studyType"),
        design=dict(design),
        enrollment_count=enrollment.get("count"),
        enrollment_type=enrollment.get("type"),
        conditions=conditions,
        keywords=keywords,
        sponsors={
            "responsible_party": sponsors_mod.get("responsibleParty") or {},
            "lead": dict(lead) if isinstance(lead, dict) else {},
            "collaborators": [dict(x) for x in collaborators if isinstance(x, dict)],
        },
        start_date=_date_struct(status, "startDateStruct"),
        start_date_type=_date_type(status, "startDateStruct"),
        primary_completion_date=_date_struct(status, "primaryCompletionDateStruct"),
        primary_completion_date_type=_date_type(status, "primaryCompletionDateStruct"),
        completion_date=_date_struct(status, "completionDateStruct"),
        completion_date_type=_date_type(status, "completionDateStruct"),
        study_first_submit_date=status.get("studyFirstSubmitDate"),
        study_first_post_date=_date_struct(status, "studyFirstPostDateStruct"),
        last_update_submit_date=status.get("lastUpdateSubmitDate"),
        last_update_post_date=_date_struct(status, "lastUpdatePostDateStruct"),
        last_update_post_date_type=_date_type(status, "lastUpdatePostDateStruct"),
        eligibility_criteria=eligibility.get("eligibilityCriteria"),
        minimum_age=eligibility.get("minimumAge"),
        maximum_age=eligibility.get("maximumAge"),
        sex=eligibility.get("sex"),
        gender_based=eligibility.get("genderBased"),
        gender_description=eligibility.get("genderDescription"),
        healthy_volunteers=eligibility.get("healthyVolunteers"),
        standard_ages=[str(x) for x in _list(eligibility.get("stdAges")) if x],
        eligibility=dict(eligibility),
        arms=arm_groups,
        interventions=interventions,
        central_contacts=central_contacts,
        overall_officials=overall_officials,
        locations=locations,
        primary_outcomes=[dict(x) for x in _list(outcomes.get("primaryOutcomes")) if isinstance(x, dict)],
        secondary_outcomes=[dict(x) for x in _list(outcomes.get("secondaryOutcomes")) if isinstance(x, dict)],
        other_outcomes=[dict(x) for x in _list(outcomes.get("otherOutcomes")) if isinstance(x, dict)],
        references=[dict(x) for x in _list(references.get("references")) if isinstance(x, dict)],
        see_also_links=[dict(x) for x in _list(references.get("seeAlsoLinks")) if isinstance(x, dict)],
        available_ipds=[dict(x) for x in _list(references.get("availIpds")) if isinstance(x, dict)],
        ipd_sharing=dict(ipd),
        oversight=dict(oversight),
        has_results=has_results,
        is_fda_regulated_drug=oversight.get("isFdaRegulatedDrug"),
        is_fda_regulated_device=oversight.get("isFdaRegulatedDevice"),
        protocol_section=dict(protocol),
        results_section=dict(raw.get("resultsSection") or {}),
        annotation_section=dict(raw.get("annotationSection") or {}),
        document_section=dict(raw.get("documentSection") or {}),
        derived_section=dict(raw.get("derivedSection") or {}),
    )
