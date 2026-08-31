#!/usr/bin/env python3
from __future__ import annotations
import json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from bridge_09d.package import source_identity_sha256,candidate_id

def main()->int:
    errors=[]
    auth=json.loads((ROOT/'09D_READONLY_AUTHORITY.json').read_text())
    if auth.get('mode')!='READ_ONLY' or auth.get('write_allowed') is not False: errors.append('09D authority pin is not read-only')
    projector=(ROOT/'warehouse/project.py').read_text()
    pg=(ROOT/'schema/frontier_postgres.sql').read_text(); bq=(ROOT/'schema/frontier_bigquery.sql').read_text()
    for forbidden in ('drug_entity','drug_alias','drug_linkage_evidence'):
        if f'"{forbidden}"' in projector or f'frontier.{forbidden} (' in pg or f'frontier.{forbidden} (' in bq:
            errors.append(f'premature canonical drug authority surface remains: {forbidden}')
    required=('drug_candidate','drug_candidate_alias','drug_candidate_linkage_evidence')
    for table in required:
        if f'frontier.{table} (' not in pg or f'frontier.{table} (' not in bq: errors.append(f'{table} missing in physical schema')
    test_sha=source_identity_sha256('frontier.drug_source_record','drugbank:DB00001')
    if candidate_id('frontier.drug_source_record','drugbank:DB00001')!='CAND:'+test_sha[:32]: errors.append('candidate deterministic ID contract mismatch')

    assertions=(ROOT/'bridge_09d/assertions.py').read_text()
    for token in ('SOURCE_UNIT_SCHEMA_VERSION','ASSERTION_SCHEMA_VERSION','UNIT:','ASSERT:','INTERP:','NOT_VERIFIED','canonical_authority'):
        if token not in assertions: errors.append(f'assertion/source-unit contract missing {token}')
    for rel in ('bridge_09d/contracts/SOURCE_UNIT_CONTRACT.md','bridge_09d/contracts/ATOMIC_ASSERTION_CONTRACT.md','bridge_09d/contracts/FULLTEXT_SEGMENTATION_CONTRACT.md','bridge_09d/contracts/ASSERTION_EXTRACTION_ENGINE_CONTRACT.md','bridge_09d/contracts/INDEPENDENT_ASSERTION_VERIFIER_CONTRACT.md','bridge_09d/contracts/SEMANTIC_VERIFIER_GOLD_CONTRACT.md','bridge_09d/contracts/SEMANTIC_REVIEW_ROUTER_CONTRACT.md','bridge_09d/contracts/SEMANTIC_FACTORY_CONTRACT.md','bridge_09d/contracts/IDENTITY_RESOLUTION_CONTRACT.md','bridge_09d/contracts/09D_READONLY_COMPARATOR_CONTRACT.md','bridge_09d/contracts/TURN6_AUDIT_PREP_CONTRACT.md'):
        if not (ROOT/rel).is_file(): errors.append(f'missing frozen extraction contract: {rel}')
    segmenter=(ROOT/'bridge_09d/source_units.py').read_text()
    for token in ('SEGMENTER_SCHEMA_VERSION','PMC_OAI_BASE','ABSTRACT_ONLY','segment_jats_xml','segment_structured_json','rights_dimensions'):
        target = segmenter if token != 'rights_dimensions' else (ROOT/'bridge_09d/package.py').read_text()
        if token not in target: errors.append(f'Turn 3 source-unit/full-text layer missing {token}')
    package=(ROOT/'bridge_09d/package.py').read_text()
    for token in ('IMPLEMENTED_OFFLINE_CERTIFIED','IMPLEMENTED_OFFLINE_CERTIFIED_PUBLIC_CANARY_PENDING','rights_dimensions_separate','raw_fulltext_payloads_embedded_in_audit_package'):
        if token not in package: errors.append(f'Turn 3 package contract missing {token}')
    engine=(ROOT/'bridge_09d/assertion_engine.py').read_text()
    for token in ('FORBIDDEN_PROPOSAL_KEYS','NOT_VERIFIED','PASS_WITH_QUARANTINE','structured_clinicaltrials_provider','candidate_resolution_performed','09d_comparison_performed'):
        if token not in engine: errors.append(f'Turn 4 assertion engine missing {token}')
    pipeline=(ROOT/'bridge_09d/assertion_pipeline.py').read_text()
    for token in ('assertions_sha256','quarantine_sha256','semantic_verification_performed','canonical_authority'):
        if token not in pipeline: errors.append(f'Turn 4 assertion pipeline missing {token}')
    for token in ('IMPLEMENTED_OFFLINE_CERTIFIED_UNVERIFIED_OUTPUT','EXTRACTOR_ASSERTIONS_REMAIN_NOT_VERIFIED','IMPLEMENTED_OFFLINE_CERTIFIED_APPEND_ONLY','APPEND_ONLY_VERIF_EVENTS','INTERFACE_IMPLEMENTED_BACKEND_NOT_CERTIFIED'):
        if token not in package: errors.append(f'Turn 5 package contract missing {token}')
    verifier=(ROOT/'bridge_09d/verifier.py').read_text()
    for token in ('VERIF:','blind_independent_review','NUMERIC_BINDING','QUALIFIER_SCOPE','RELATIONSHIP_BINDING','FRONTIER_ADJUDICATION','PROVENANCE_INCOMPLETE'):
        if token not in verifier: errors.append(f'Turn 5 independent verifier missing {token}')
    vp=(ROOT/'bridge_09d/verifier_pipeline.py').read_text()
    for token in ('verification_events_sha256','assertions_mutated','blind_independent_review','canonical_authority'):
        if token not in vp: errors.append(f'Turn 5 verifier pipeline missing {token}')
    br=(ROOT/'bridge_09d/blind_recall.py').read_text(); brp=(ROOT/'bridge_09d/blind_recall_pipeline.py').read_text(); sr=(ROOT/'bridge_09d/semantic_router.py').read_text()
    for token in ('independent_of_primary_extractor','RECALL_ONLY_CANDIDATE','SAME_EVIDENCE_SEMANTIC_DISAGREEMENT','automatic_repair_allowed'):
        if token not in br: errors.append(f'Turn 5 blind recall missing {token}')
    for token in ('primary_assertions_visible_during_recall','recall_assertions_sha256','reconciliation_sha256','canonical_authority'):
        if token not in brp: errors.append(f'Turn 5 blind recall pipeline missing {token}')
    for token in ('SEMCASE:','FRONTIER_ADJUDICATION','RECALL_ONLY_CANDIDATE','automatic_action_allowed','canonical_authority'):
        if token not in sr: errors.append(f'Turn 5 semantic router missing {token}')
    sf=(ROOT/'bridge_09d/semantic_factory.py').read_text()
    for token in ('SEMRUN:','verify_assertions','run_blind_recall','route_semantic_review','mass_extraction_authorized'):
        if token not in sf: errors.append(f'Turn 5 semantic factory missing {token}')
    ir=(ROOT/'bridge_09d/identity_resolution.py').read_text(); cmp=(ROOT/'bridge_09d/comparator_09d.py').read_text(); t6=(ROOT/'bridge_09d/turn6_factory.py').read_text()
    for token in ('frontier.assertion_entity_surface','DOMAIN_AMBIGUOUS','REGISTERED_FOR_READONLY_LOOKUP','candidate_to_canonical_assignment_performed'):
        if token not in ir: errors.append(f'Turn 6 identity resolver missing {token}')
    for token in ('mode=ro&immutable=1','PRAGMA query_only=ON','EXACT_EXISTING','CONTRADICTORY','CONTEXT_DIFFERENT','09d_mutation_performed'):
        if token not in cmp: errors.append(f'Turn 6 read-only comparator missing {token}')
    for token in ('run_turn6_audit_prep','candidate_to_canonical_assignment_performed','09d_comparison_performed','mass_extraction_authorized'):
        if token not in t6: errors.append(f'Turn 6 audit prep factory missing {token}')
    contract=(ROOT/'09D_EXTRACTION_BOUNDARY_CONTRACT.md').read_text()
    for token in ('direct_09d_insert_allowed = false','canonical_authority = false','generation_eligible = false','public_eligible = false'):
        if token not in contract: errors.append(f'boundary contract missing {token}')
    report={'status':'PASS' if not errors else 'FAIL','09d_repo_write_performed':False,'direct_09d_insert_allowed':False,'candidate_id_example':candidate_id('frontier.drug_source_record','drugbank:DB00001'),'errors':errors}
    (ROOT/'09D_ALIGNMENT_VALIDATION.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print('09D ALIGNMENT:',report['status']); print('DIRECT 09D INSERT: FALSE'); print('09D REPO WRITE: FALSE')
    if errors:
        for e in errors: print('FAIL |',e)
    return 0 if not errors else 1
if __name__=='__main__': raise SystemExit(main())
