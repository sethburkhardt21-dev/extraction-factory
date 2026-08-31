"""Configuration for the ClinicalTrials.gov v2 extraction engine."""
from __future__ import annotations
import pathlib

PRESETS = {
    "all": None,
    "completed_interventional": "AREA[OverallStatus]COMPLETED AND AREA[StudyType]INTERVENTIONAL",
    "covid19": "AREA[Condition]COVID-19",
    "cancer": "AREA[Condition]cancer",
    "alzheimer_recruiting": "AREA[Condition]Alzheimer AND AREA[OverallStatus]RECRUITING",
    "phase3": "AREA[Phase]PHASE3",
    "industry_sponsored": "AREA[SponsorClass]INDUSTRY",
    "2024_updates_posted": "AREA[LastUpdatePostDate]RANGE[01/01/2024,12/31/2024]",
}

DEFAULT_OUTPUT = pathlib.Path("workspace/data")
DEFAULT_RATE_PER_SEC = 2.0  # conservative local policy; CTG docs do not publish a hard RPS contract
DEFAULT_PAGE_SIZE = 1000
API_BASE = "https://clinicaltrials.gov/api/v2/studies"
API_BULK_DOWNLOAD = "https://clinicaltrials.gov/api/v2/studies/download"
API_VERSION_ENDPOINT = "https://clinicaltrials.gov/api/v2/version"
