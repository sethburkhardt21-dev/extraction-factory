from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class WorkState(str, Enum):
    REGISTERED = "REGISTERED"
    READY = "READY"
    LEASED = "LEASED"
    RUNNING = "RUNNING"
    STAGED = "STAGED"
    VALIDATING = "VALIDATING"
    ACCEPTED = "ACCEPTED"
    RETRY = "RETRY"
    ESCALATE = "ESCALATE"
    DEFERRED = "DEFERRED"
    FAILED = "FAILED"
    SUPERSEDED = "SUPERSEDED"
    CANCELLED = "CANCELLED"


class GateResult(str, Enum):
    PASS = "PASS"
    FAIL_BLOCKING = "FAIL_BLOCKING"
    FAIL_REVIEW_REQUIRED = "FAIL_REVIEW_REQUIRED"
    NOT_RUN = "NOT_RUN"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    BLOCKED_EXTERNAL = "BLOCKED_EXTERNAL"


class ReviewOutcome(str, Enum):
    SUPPORTED = "SUPPORTED"
    REPAIRABLE = "REPAIRABLE"
    AMBIGUOUS_DEFER = "AMBIGUOUS_DEFER"
    UNSUPPORTED = "UNSUPPORTED"


class CandidateStatus(str, Enum):
    SOURCE_ASSERTION_CANDIDATE = "SOURCE_ASSERTION_CANDIDATE"


class ReviewState(str, Enum):
    UNREVIEWED = "UNREVIEWED"
    REVIEWED = "REVIEWED"
    NEEDS_SPECIALIST = "NEEDS_SPECIALIST"
    DEFERRED = "DEFERRED"


class CanonicalState(str, Enum):
    NON_CANONICAL = "NON_CANONICAL"
    CANONICAL = "CANONICAL"


@dataclass(frozen=True)
class WorkerIdentity:
    provider: str
    model_alias: str
    underlying_family: str
    observed_version: str
    role: str
    certification_status: str = "UNBENCHMARKED"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SourceUnit:
    source_unit_id: str
    source_id: str
    source_version_id: str
    source_sha256: str
    unit_type: str
    content_representation: str
    locator: Dict[str, Any]
    content_sha256: str
    content: str
    rights_metadata: Dict[str, Any] = field(default_factory=dict)
    process_metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "SourceUnit":
        return cls(**{k: value.get(k) for k in cls.__dataclass_fields__})

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AssertionCandidate:
    candidate_id: str
    source_unit_id: str
    source_id: str
    source_version_id: str
    source_sha256: str
    locator: Dict[str, Any]
    evidence: str
    evidence_sha256: str
    proposition: str
    subject: Optional[str] = None
    predicate: Optional[str] = None
    object_value: Optional[str] = None
    numeric_values: List[Dict[str, Any]] = field(default_factory=list)
    qualifiers: List[str] = field(default_factory=list)
    polarity: str = "AFFIRMATIVE"
    certainty: str = "ASSERTED"
    conditionality: Optional[str] = None
    temporality: Optional[str] = None
    comparison: Optional[str] = None
    relationship_direction: Optional[str] = None
    table_binding_state: str = "NOT_APPLICABLE"
    visual_binding_state: str = "NOT_APPLICABLE"
    cross_page_state: str = "LOCAL"
    originating_capsule_id: str = ""
    originating_run_id: str = ""
    parent_artifact_sha256: str = ""
    worker_identity: Dict[str, Any] = field(default_factory=dict)
    origin_pass: str = "PRIMARY"
    candidate_status: str = CandidateStatus.SOURCE_ASSERTION_CANDIDATE.value
    review_state: str = ReviewState.UNREVIEWED.value
    canonical_state: str = CanonicalState.NON_CANONICAL.value
    uncertainty_flags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "AssertionCandidate":
        fields = cls.__dataclass_fields__
        return cls(**{k: value.get(k) for k in fields})

    def validate_invariants(self) -> List[str]:
        errors: List[str] = []
        if self.candidate_status != CandidateStatus.SOURCE_ASSERTION_CANDIDATE.value:
            errors.append("candidate_status_must_remain_source_assertion_candidate")
        if self.canonical_state != CanonicalState.NON_CANONICAL.value:
            errors.append("extractor_candidate_must_be_noncanonical")
        if not self.source_unit_id:
            errors.append("missing_source_unit_id")
        if not self.evidence:
            errors.append("missing_evidence")
        if not self.evidence_sha256:
            errors.append("missing_evidence_sha256")
        if not self.proposition:
            errors.append("missing_proposition")
        if not self.originating_run_id:
            errors.append("missing_originating_run_id")
        return errors


@dataclass
class EvidenceFamily:
    family_id: str
    source_unit_id: str
    member_candidate_ids: List[str]
    propositions: List[str]
    origins: List[str]
    evidence_hashes: List[str]
    disagreement_types: List[str]
    specialist_requirements: List[str]
    review_state: str = "UNREVIEWED"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SpecialistReceipt:
    receipt_id: str
    family_id: str
    specialist_type: str
    outcome: str
    rationale: str
    candidate_ids: List[str]
    proposed_repairs: List[Dict[str, Any]] = field(default_factory=list)
    unresolved_flags: List[str] = field(default_factory=list)
    worker_identity: Dict[str, Any] = field(default_factory=dict)
    run_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Gate:
    name: str
    result: str
    detail: str = ""
    required: bool = True
    bounded_queue: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
