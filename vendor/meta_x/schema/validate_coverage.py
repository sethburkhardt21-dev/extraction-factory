#!/usr/bin/env python3
"""Machine-checkable source-to-warehouse coverage contract.

A field is covered when it is either projected into an analytical Silver surface
or deterministically recoverable from retained/pinned Bronze evidence. The latter
is deliberate: frontier readiness does not require flattening every upstream field,
but it does require never needing to re-download a source merely to reparse it.
"""
from __future__ import annotations
from dataclasses import fields
import json, sys
from pathlib import Path
from typing import Dict, List
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from clinicaltrials.canonical.clinicaltrials.models import CanonicalStudy
from pubmed_rag.metadata_schema import PubMedRecordFull

OUT=ROOT/'schema/SCHEMA_COVERAGE.json'

CTG_CHILD={
    'phase':'ctg_phase','conditions':'ctg_condition','keywords':'ctg_keyword','sponsors':'ctg_sponsor',
    'arms':'ctg_arm','interventions':'ctg_intervention','central_contacts':'ctg_contact',
    'overall_officials':'ctg_contact','locations':'ctg_location','primary_outcomes':'ctg_outcome',
    'secondary_outcomes':'ctg_outcome','other_outcomes':'ctg_outcome','references':'ctg_reference',
    'available_ipds':'ctg_available_ipd',
}
CTG_RECORD=set('''nct_id brief_title official_title acronym nct_id_aliases org_study_id_info secondary_id_infos organization brief_summary detailed_description overall_status why_stopped expanded_access_info study_type design enrollment_count enrollment_type start_date start_date_type primary_completion_date primary_completion_date_type completion_date completion_date_type study_first_submit_date study_first_post_date last_update_submit_date last_update_post_date last_update_post_date_type eligibility_criteria minimum_age maximum_age sex gender_based gender_description healthy_volunteers standard_ages eligibility see_also_links ipd_sharing oversight has_results is_fda_regulated_drug is_fda_regulated_device'''.split())
CTG_RAW={'protocol_section':'ctg_study_record.protocol_raw','results_section':'ctg_study_record.results_raw','annotation_section':'ctg_study_record.annotation_raw','document_section':'ctg_study_record.document_raw','derived_section':'ctg_study_record.derived_raw'}

PUBMED_CHILD={'authors':'pubmed_author','mesh_headings':'pubmed_mesh_heading'}
PUBMED_RECORD=set('''record_type pmid doi pmc_id version title abstract abstract_sections journal journal_abbrev journal_issn volume issue pages pub_date article_date pubmed_pub_dates date_created date_completed date_revised keywords publication_types languages chemicals grants article_ids references publication_status book_metadata raw_xml'''.split())
PUBMED_SNAPSHOT={'retrieval_query':'pubmed_snapshot.retrieval_queries','retrieval_queries':'pubmed_snapshot.retrieval_queries','retrieved_at':'pubmed_snapshot.retrieved_at'}
PUBMED_CORE={'retrieval_source':'ingestion_run.mode/provenance','source_url':'source_record.source_url','run_id':'ingestion_run.run_id','parser_version':'canonical_record.parser_version','canonical_schema_version':'canonical_record.canonical_schema_version','source_record_sha256':'source_record.source_record_sha256'}
# Parser convenience flags that are reproducible from the immutable raw XML even if
# we deliberately do not allocate first-class warehouse columns for them.
PUBMED_REPARSE={'title_truncated':'pubmed_record.raw_xml'}

PREPRINT_FIELDS=set('''doi server title authors author_corresponding author_corresponding_institution category date version type license abstract funding published jatsxml biorxiv_doi medrxiv_doi source_record_sha256 source_payload'''.split())
PREPRINT_FIRST=set('''doi server title authors author_corresponding author_corresponding_institution category date version license published source_record_sha256 source_payload'''.split())

FORBIDDEN_PUBMED_ENRICHMENT={
    'embedding_input_text','embedding_model','embedding_model_revision','embedding_dim','embedding_normalized',
    'embedding_hash','embedding_vector','anesthesia_classification','anesthesia_subspecialty',
    'dedup_key_title_norm','dedup_key_doi_norm','duplicate_of','is_duplicate',
}

def _entry(field:str,route:str,coverage:str) -> Dict[str,str]:
    return {'field':field,'coverage':coverage,'route':route}

def clinicaltrials() -> Dict:
    names=[f.name for f in fields(CanonicalStudy)]
    rows=[]; missing=[]
    for name in names:
        if name in CTG_CHILD: rows.append(_entry(name,CTG_CHILD[name],'first_class_child_table'))
        elif name in CTG_RECORD: rows.append(_entry(name,'ctg_study_record','first_class_or_structured_record'))
        elif name in CTG_RAW: rows.append(_entry(name,CTG_RAW[name],'lossless_raw_section'))
        else: missing.append(name)
    return {'canonical_fields':len(names),'covered_fields':len(rows),'unaccounted_fields':missing,'fields':rows,'lossless_reparse_invariant':'exact API response bytes retained for paginated runs or exact bulk ZIP retained for bulk runs; complete v2 protocol/results/annotation/document/derived sections retained in Silver'}

def pubmed() -> Dict:
    names=list(PubMedRecordFull.model_fields)
    forbidden=sorted(set(names)&FORBIDDEN_PUBMED_ENRICHMENT)
    rows=[]; missing=[]
    for name in names:
        if name in PUBMED_CHILD: rows.append(_entry(name,PUBMED_CHILD[name],'first_class_child_table'))
        elif name in PUBMED_RECORD: rows.append(_entry(name,'pubmed_record','first_class_or_structured_record'))
        elif name in PUBMED_SNAPSHOT: rows.append(_entry(name,PUBMED_SNAPSHOT[name],'snapshot_provenance'))
        elif name in PUBMED_CORE: rows.append(_entry(name,PUBMED_CORE[name],'generic_provenance_core'))
        elif name in PUBMED_REPARSE: rows.append(_entry(name,PUBMED_REPARSE[name],'lossless_reparse'))
        else: missing.append(name)
    return {'canonical_fields':len(names),'covered_fields':len(rows),'unaccounted_fields':missing,'forbidden_enrichment_fields_present':forbidden,'fields':rows,'lossless_reparse_invariant':'exact ESearch/EFetch HTTP response bytes retained in Bronze transport artifacts; per-record semantic XML retained in Bronze/Silver for deterministic reparse'}

def preprint() -> Dict:
    rows=[]
    for name in sorted(PREPRINT_FIELDS):
        coverage='first_class_or_structured_record' if name in PREPRINT_FIRST else 'lossless_source_payload'
        route='preprint_record' if name in PREPRINT_FIRST else 'preprint_record.source_payload'
        rows.append(_entry(name,route,coverage))
    return {'normalized_fields':len(PREPRINT_FIELDS),'covered_fields':len(rows),'unaccounted_fields':[],'fields':rows,'lossless_reparse_invariant':'exact details API HTTP response bytes retained in Bronze transport artifacts and exact parsed collection item retained as source_payload for every version'}

def drug() -> Dict:
    # Drug sources are heterogeneous/licensed; the contract is artifact-based rather
    # than pretending they share one universal source schema.
    invariants=[
        {'source':'drugbank','bronze_evidence':'licensed XML artifact SHA-256 + pinned release/version + per-record XML-element SHA-256','warehouse_route':'drug_source_record.payload'},
        {'source':'rxnorm','bronze_evidence':'exact RxNav JSON response retained as source_payload + SHA-256','warehouse_route':'drug_source_record.payload'},
        {'source':'livertox','bronze_evidence':'retained source_payload/source_text or independently pinned source snapshot + SHA-256','warehouse_route':'drug_source_record.payload'},
    ]
    return {'source_contracts':len(invariants),'unaccounted_sources':[],'sources':invariants,'lossless_reparse_invariant':'every production source artifact is retained or cryptographically pinned; linkage evidence never substitutes for source evidence'}

def main() -> int:
    sources={'clinicaltrials':clinicaltrials(),'pubmed':pubmed(),'preprints':preprint(),'drug_references':drug()}
    failures=[]
    for name,section in sources.items():
        if section.get('unaccounted_fields'): failures.append(f"{name}: unaccounted fields {section['unaccounted_fields']}")
        if section.get('unaccounted_sources'): failures.append(f"{name}: unaccounted sources {section['unaccounted_sources']}")
        if section.get('forbidden_enrichment_fields_present'): failures.append(f"{name}: enrichment contamination {section['forbidden_enrichment_fields_present']}")
    report={
        'schema_coverage_version':'frontier-schema-coverage-1.0',
        'status':'PASS' if not failures else 'FAIL',
        'principle':'project high-value fields; retain/pin lossless Bronze evidence for deterministic reparsing of everything else',
        'sources':sources,
        'failures':failures,
    }
    OUT.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(f"SCHEMA COVERAGE: {report['status']}")
    for name,section in sources.items():
        count=section.get('canonical_fields',section.get('normalized_fields',section.get('source_contracts')))
        print(f"{name}: {count} fields/contracts; unaccounted={len(section.get('unaccounted_fields',section.get('unaccounted_sources',[])))}")
    return 0 if not failures else 1

if __name__=='__main__': raise SystemExit(main())
