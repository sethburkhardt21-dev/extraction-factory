# Hermes Advanced v1.1 Test Report

- Overall: **PASS**
- Return code: `0`
- Duration: `8.613` seconds

```text
{
  "applied": true,
  "automatic_time_expiry": "NOT_DEFINED_BY_ARCHITECTURE",
  "certification_key": "OLLAMA|model|PRIMARY|W2|S1|BENCH",
  "event_id": "CERTLIFE-fd813b93ed2af430b8e8496d",
  "from_status": "CERTIFIED_WITH_LIMITS",
  "incident_ref": "INC-9",
  "invalidated_evidence_match_mode": "FULL_FINGERPRINT",
  "invalidated_evidence_sha256": "f57209c3f6e4f11cdd88394368a3af59893b150c47a64ae00240d5ed3c1fec13",
  "reason": "confirmed regression",
  "retirement_tombstone": false,
  "runtime_authority_after_transition": false,
  "schema_version": "hermes-certification-lifecycle-transition-1.3",
  "to_status": "SUSPENDED"
}
registry updated: C:\Users\sethb\AppData\Local\Temp\tmpjnmctuhf\registry.json
NOTE: registry is protected production state — rerun tests and certify-build after this change.
{
  "applied": false,
  "automatic_time_expiry": "NOT_DEFINED_BY_ARCHITECTURE",
  "certification_key": "OLLAMA|model|PRIMARY|W2|S1|BENCH",
  "event_id": "CERTLIFE-26fea84e98cec10c5cb89940",
  "from_status": "CERTIFIED_WITH_LIMITS",
  "incident_ref": null,
  "invalidated_evidence_match_mode": "FULL_FINGERPRINT",
  "invalidated_evidence_sha256": "f57209c3f6e4f11cdd88394368a3af59893b150c47a64ae00240d5ed3c1fec13",
  "reason": "dry-run test",
  "retirement_tombstone": false,
  "runtime_authority_after_transition": false,
  "schema_version": "hermes-certification-lifecycle-transition-1.3",
  "to_status": "SUSPENDED"
}
{
  "primary": {
    "model": "primary",
    "provider": "OLLAMA",
    "status": "BLOCKED_EXTERNAL",
    "failures": [
      "model_version_binding_not_certifiable:policy=CLI_OBSERVED:observed=UNOBSERVED"
    ],
    "observed_version": "UNOBSERVED",
    "registry_authority_sha256": "3955141318edbc9839ca2e8cfac73717497fc4c816ebce4e385a03ee85b9c858",
    "candidate_semantic_sha256": "9e49059ca2dce18ccbcfbc755b8f3338468250dbec9f3a3930fb7cedf849d2fd"
  },
  "blind": {
    "model": "blind",
    "provider": "OLLAMA",
    "status": "REJECTED",
    "failures": [
      "omission_recovery>=0.50: NOT_MEASURED",
      "useful_new_precision>=0.70: NOT_MEASURED"
    ],
    "observed_version": "UNOBSERVED",
    "registry_authority_sha256": "f03bb72df531cf24e10899f39e94ccd38383ed0500545f473cc0e4338a0ad10b",
    "candidate_semantic_sha256": "abba654a93aaf2a729b6b6f2ad9f30179652322197634e5948b055abdbb24210",
    "primary_candidate_semantic_sha256": "9e49059ca2dce18ccbcfbc755b8f3338468250dbec9f3a3930fb7cedf849d2fd"
  },
  "registry_keys_written": [
    "OLLAMA|blind|BLIND_RECALL|W2|S1|MACHINES_P0299_P0301_SOURCE_FIRST_v1",
    "OLLAMA|primary|PRIMARY|W2|S1|MACHINES_P0299_P0301_SOURCE_FIRST_v1"
  ],
  "reactivation_blocks": {},
  "input_recomputation_verified": true,
  "verification": {
    "verification_schema_version": "hermes-role-certification-input-verification-1.4",
    "recomputation_verified": true,
    "W2_S1_scope": [
      "U1",
      "U2"
    ],
    "primary": {
      "score_path": "C:\\Users\\sethb\\AppData\\Local\\Temp\\tmp7zk1158e\\primary_score.json",
      "score_sha256": "f5182dfef3a170a466e157af5d0bf79122d20eb7a4e08e8cae19d3f329dd8eb7",
      "candidate_file_sha256": "28def7363299dc4444491eae19373d983d1549d113cd75ad180365932f3e41f0",
      "primary_candidate_file_sha256": null,
      "source_units_sha256": "da8e2a442fe34b92f03c2b976bb2764d1a87713d0a6b2d2500bf8cded322f9b7",
      "reference_sha256": "18f7fcb9bbd0845fcb1755c53bf24bc4b9ffaf69eb0305cbf747493deddf2373",
      "gold_manifest_sha256": "9d1495df8505529ffe51b2af874ac081b708be1aa75e91f66276cfa0fcbb71dd",
      "replay_equivalent": true,
      "registry_sha256_at_score": "4132a22f62d718107dc2f6ee60be9f8e8d0023c32ecce6935cef73bb8b73ba1f",
      "registry_sha256_current": "4132a22f62d718107dc2f6ee60be9f8e8d0023c32ecce6935cef73bb8b73ba1f",
      "registry_sha256_changed": false,
      "registry_authority_projection": {
        "schema_version": "hermes-scoring-authority-projection-1.0",
        "scored_identity": {
          "provider": "OLLAMA",
          "model_alias": "primary",
          "underlying_family": "PRIMARY",
          "empirical_semantic_model": true,
          "independence_group": "PRIMARY",
          "observed_version_policy": "CLI_OBSERVED",
          "observed_version": "UNOBSERVED",
          "version_binding_certifiable": false
        },
        "primary_baseline_identity": null
      },
      "registry_authority_sha256": "3955141318edbc9839ca2e8cfac73717497fc4c816ebce4e385a03ee85b9c858"
    },
    "blind": {
      "score_path": "C:\\Users\\sethb\\AppData\\Local\\Temp\\tmp7zk1158e\\blind_score.json",
      "score_sha256": "02951fa3c2eb46d316176fc67b1e0aaf9ed87fbf905ee8bef9372bb1e0424030",
      "candidate_file_sha256": "469a9414281fa59fb763c042812161f55bd4dc2adc200f00824e839640e6716f",
      "primary_candidate_file_sha256": "28def7363299dc4444491eae19373d983d1549d113cd75ad180365932f3e41f0",
      "source_units_sha256": "da8e2a442fe34b92f03c2b976bb2764d1a87713d0a6b2d2500bf8cded322f9b7",
      "reference_sha256": "18f7fcb9bbd0845fcb1755c53bf24bc4b9ffaf69eb0305cbf747493deddf2373",
      "gold_manifest_sha256": "9d1495df8505529ffe51b2af874ac081b708be1aa75e91f66276cfa0fcbb71dd",
      "replay_equivalent": true,
      "registry_sha256_at_score": "4132a22f62d718107dc2f6ee60be9f8e8d0023c32ecce6935cef73bb8b73ba1f",
      "registry_sha256_current": "4132a22f62d718107dc2f6ee60be9f8e8d0023c32ecce6935cef73bb8b73ba1f",
      "registry_sha256_changed": false,
      "registry_authority_projection": {
        "schema_version": "hermes-scoring-authority-projection-1.0",
        "scored_identity": {
          "provider": "OLLAMA",
          "model_alias": "blind",
          "underlying_family": "BLIND",
          "empirical_semantic_model": true,
          "independence_group": "BLIND",
          "observed_version_policy": "CLI_OBSERVED",
          "observed_version": "UNOBSERVED",
          "version_binding_certifiable": false
        },
        "primary_baseline_identity": {
          "provider": "OLLAMA",
          "model_alias": "primary",
          "underlying_family": "PRIMARY",
          "empirical_semantic_model": true,
          "independence_group": "PRIMARY",
          "observed_version_policy": "CLI_OBSERVED",
          "observed_version": "UNOBSERVED",
          "version_binding_certifiable": false
        }
      },
      "registry_authority_sha256": "f03bb72df531cf24e10899f39e94ccd38383ed0500545f473cc0e4338a0ad10b"
    }
  },
  "applied": false
}

test_authority_context_changes_when_comparison_bytes_change (test_09d_authority_binding.AuthorityBindingTests.test_authority_context_changes_when_comparison_bytes_change) ... ok
test_strict_projection_accepts_verified_bound_target (test_09d_authority_binding.AuthorityBindingTests.test_strict_projection_accepts_verified_bound_target) ... ok
test_strict_projection_detects_target_schema_drift_after_comparison (test_09d_authority_binding.AuthorityBindingTests.test_strict_projection_detects_target_schema_drift_after_comparison) ... ok
test_strict_projection_rejects_unverified_database_hash (test_09d_authority_binding.AuthorityBindingTests.test_strict_projection_rejects_unverified_database_hash) ... ok
test_equal_temperature_preserves_support (test_09d_numeric_context_guard.NumericContextEvaluationTests.test_equal_temperature_preserves_support) ... ok
test_matching_ambient_pressure_context_can_pass (test_09d_numeric_context_guard.NumericContextEvaluationTests.test_matching_ambient_pressure_context_can_pass) ... ok
test_missing_temperature_on_one_side_requires_review (test_09d_numeric_context_guard.NumericContextEvaluationTests.test_missing_temperature_on_one_side_requires_review) ... ok
test_no_structured_target_does_not_invent_context_binding (test_09d_numeric_context_guard.NumericContextEvaluationTests.test_no_structured_target_does_not_invent_context_binding) ... ok
test_target_pressure_is_not_misclassified_as_context (test_09d_numeric_context_guard.NumericContextEvaluationTests.test_target_pressure_is_not_misclassified_as_context) ... ok
test_temperature_conflict_downgrades_support (test_09d_numeric_context_guard.NumericContextEvaluationTests.test_temperature_conflict_downgrades_support) ... ok
test_guard_downgrades_projection_and_preserves_original_state (test_09d_numeric_context_guard.NumericContextGuardIntegrationTests.test_guard_downgrades_projection_and_preserves_original_state) ... ok
test_ambiguous_exact_alias_cannot_support_or_contradict (test_09d_optimization.ComparatorIdentityTests.test_ambiguous_exact_alias_cannot_support_or_contradict) ... ok
test_context_difference_suppresses_numeric_contradiction (test_09d_optimization.ComparatorIdentityTests.test_context_difference_suppresses_numeric_contradiction) ... ok
test_decimal_formatting_equivalence_does_not_contradict (test_09d_optimization.ComparatorIdentityTests.test_decimal_formatting_equivalence_does_not_contradict) ... ok
test_disjoint_ranges_can_contradict_when_identity_and_context_match (test_09d_optimization.ComparatorIdentityTests.test_disjoint_ranges_can_contradict_when_identity_and_context_match) ... ok
test_exact_alias_and_predicate_can_support (test_09d_optimization.ComparatorIdentityTests.test_exact_alias_and_predicate_can_support) ... ok
test_same_identity_same_unit_different_value_is_contradiction (test_09d_optimization.ComparatorIdentityTests.test_same_identity_same_unit_different_value_is_contradiction) ... ok
test_scalar_inside_range_is_overlap_not_contradiction (test_09d_optimization.ComparatorIdentityTests.test_scalar_inside_range_is_overlap_not_contradiction) ... ok
test_structured_numeric_binding_beats_neighbor_number_capture (test_09d_optimization.ComparatorIdentityTests.test_structured_numeric_binding_beats_neighbor_number_capture) ... ok
test_unique_family_predicate_tail_resolves_namespaced_code (test_09d_optimization.ComparatorIdentityTests.test_unique_family_predicate_tail_resolves_namespaced_code) ... ok
test_carrier_partition_and_default_scope_exclude_motion2 (test_09d_optimization.Motion2ProjectionTests.test_carrier_partition_and_default_scope_exclude_motion2) ... ok
test_projection_rejects_all_carrier_comparison_as_cycle_unsafe (test_09d_optimization.Motion2ProjectionTests.test_projection_rejects_all_carrier_comparison_as_cycle_unsafe) ... ok
test_schema_capability_and_projection_remain_non_writing (test_09d_optimization.Motion2ProjectionTests.test_schema_capability_and_projection_remain_non_writing) ... ok
test_contract_is_stable_for_unchanged_target_schema (test_09d_target_contract.Motion2TargetContractTests.test_contract_is_stable_for_unchanged_target_schema) ... ok
test_projection_binds_every_row_to_same_target_contract (test_09d_target_contract.Motion2TargetContractTests.test_projection_binds_every_row_to_same_target_contract) ... ok
test_relevant_index_change_changes_motion2_contract (test_09d_target_contract.Motion2TargetContractTests.test_relevant_index_change_changes_motion2_contract) ... ok
test_relevant_target_schema_change_changes_motion2_contract (test_09d_target_contract.Motion2TargetContractTests.test_relevant_target_schema_change_changes_motion2_contract) ... ok
test_unrelated_schema_change_does_not_change_motion2_contract (test_09d_target_contract.Motion2TargetContractTests.test_unrelated_schema_change_does_not_change_motion2_contract) ... ok
test_all_known_leakage_keys_removed (test_adversarial_mutations.BlindInjectionTests.test_all_known_leakage_keys_removed) ... ok
test_authored_status_input_is_ignored_because_api_only_uses_gates (test_adversarial_mutations.ReadinessMutationTests.test_authored_status_input_is_ignored_because_api_only_uses_gates) ... ok
test_missing_receipt_not_run_blocks (test_adversarial_mutations.ReadinessMutationTests.test_missing_receipt_not_run_blocks) ... ok
test_unresolved_p0_blocks (test_adversarial_mutations.ReadinessMutationTests.test_unresolved_p0_blocks) ... ok
test_direction_cue_loss_detected (test_adversarial_mutations.SemanticMutationTests.test_direction_cue_loss_detected) ... ok
test_dropped_may_detected (test_adversarial_mutations.SemanticMutationTests.test_dropped_may_detected) ... ok
test_dropped_negation_detected (test_adversarial_mutations.SemanticMutationTests.test_dropped_negation_detected) ... ok
test_numeric_literal_loss_detected (test_adversarial_mutations.SemanticMutationTests.test_numeric_literal_loss_detected) ... ok
test_blind_certificate_cannot_move_to_changed_primary_weights (test_blind_pair_certification.BlindPairCertificationTests.test_blind_certificate_cannot_move_to_changed_primary_weights) ... ok
test_blind_certificate_cannot_move_to_different_primary_alias (test_blind_pair_certification.BlindPairCertificationTests.test_blind_certificate_cannot_move_to_different_primary_alias) ... ok
test_exact_scored_primary_pair_passes (test_blind_pair_certification.BlindPairCertificationTests.test_exact_scored_primary_pair_passes) ... ok
test_missing_runtime_primary_pair_context_fails_closed (test_blind_pair_certification.BlindPairCertificationTests.test_missing_runtime_primary_pair_context_fails_closed) ... ok
test_mutated_primary_registry_authority_invalidates_blind_pair (test_blind_pair_certification.BlindPairCertificationTests.test_mutated_primary_registry_authority_invalidates_blind_pair) ... ok
test_noncertifiable_primary_baseline_version_invalidates_blind_pair (test_blind_pair_certification.BlindPairCertificationTests.test_noncertifiable_primary_baseline_version_invalidates_blind_pair) ... ok
test_primary_certificate_does_not_require_blind_pair_context (test_blind_pair_certification.BlindPairCertificationTests.test_primary_certificate_does_not_require_blind_pair_context) ... ok
test_build_blind_request_never_carries_contamination (test_blindness_semantics.BlindnessTests.test_build_blind_request_never_carries_contamination) ... ok
test_nested_forbidden_key_is_rejected (test_blindness_semantics.BlindnessTests.test_nested_forbidden_key_is_rejected) ... ok
test_positive_allowlist_drops_eight_injections (test_blindness_semantics.BlindnessTests.test_positive_allowlist_drops_eight_injections) ... ok
test_numeric_literal_preserves_unit_and_range (test_blindness_semantics.LiteralTests.test_numeric_literal_preserves_unit_and_range) ... ok
test_qualifiers_detect_may_when_not (test_blindness_semantics.LiteralTests.test_qualifiers_detect_may_when_not) ... ok
test_relationship_direction_inventory (test_blindness_semantics.LiteralTests.test_relationship_direction_inventory) ... ok
test_extractor_cannot_set_canonical (test_blindness_semantics.SemanticTests.test_extractor_cannot_set_canonical) ... ok
test_fixture_primary_and_blind_are_noncanonical (test_blindness_semantics.SemanticTests.test_fixture_primary_and_blind_are_noncanonical) ... ok
test_non_source_evidence_rejected (test_blindness_semantics.SemanticTests.test_non_source_evidence_rejected) ... ok
test_family_groups_exact_evidence_only (test_blindness_semantics.UnionTests.test_family_groups_exact_evidence_only) ... ok
test_table_is_routed_to_specialist_queue (test_blindness_semantics.UnionTests.test_table_is_routed_to_specialist_queue) ... ok
test_union_preserves_distinct_candidate_origins (test_blindness_semantics.UnionTests.test_union_preserves_distinct_candidate_origins) ... ok
test_apply_requires_expect_status (test_certification_lifecycle.GovernedLifecycleMutationTests.test_apply_requires_expect_status) ... refusing --apply without --expect-status compare-and-set assertion
ok
test_apply_writes_audited_transition (test_certification_lifecycle.GovernedLifecycleMutationTests.test_apply_writes_audited_transition) ... ok
test_compare_and_set_rejects_stale_operator_state (test_certification_lifecycle.GovernedLifecycleMutationTests.test_compare_and_set_rejects_stale_operator_state) ... ok
test_dry_run_does_not_mutate_registry (test_certification_lifecycle.GovernedLifecycleMutationTests.test_dry_run_does_not_mutate_registry) ... ok
test_proposal_appends_top_level_audit_event (test_certification_lifecycle.GovernedLifecycleMutationTests.test_proposal_appends_top_level_audit_event) ... ok
test_retirement_creates_terminal_tombstone (test_certification_lifecycle.GovernedLifecycleMutationTests.test_retirement_creates_terminal_tombstone) ... ok
test_unrelated_certification_remains_active_after_one_is_suspended (test_certification_lifecycle.GovernedLifecycleMutationTests.test_unrelated_certification_remains_active_after_one_is_suspended) ... ok
test_architecture_lifecycle_states_are_representable (test_certification_lifecycle.LifecycleStateTests.test_architecture_lifecycle_states_are_representable) ... ok
test_downward_transition_records_reason_and_history (test_certification_lifecycle.LifecycleStateTests.test_downward_transition_records_reason_and_history) ... ok
test_only_certified_states_confer_authority (test_certification_lifecycle.LifecycleStateTests.test_only_certified_states_confer_authority) ... ok
test_promotions_are_not_available_through_lifecycle_policy (test_certification_lifecycle.LifecycleStateTests.test_promotions_are_not_available_through_lifecycle_policy) ... ok
test_reason_is_mandatory (test_certification_lifecycle.LifecycleStateTests.test_reason_is_mandatory) ... ok
test_retired_is_terminal (test_certification_lifecycle.LifecycleStateTests.test_retired_is_terminal) ... ok
test_certificate_entry_carries_hashed_authority_projection (test_certification_replay_lifecycle.CertifierReplayIntegrationTests.test_certificate_entry_carries_hashed_authority_projection) ... ok
test_recompute_accepts_registry_mutation_when_authority_is_unchanged (test_certification_replay_lifecycle.CertifierReplayIntegrationTests.test_recompute_accepts_registry_mutation_when_authority_is_unchanged) ... ok
test_recompute_rejects_current_identity_drift_even_if_registry_sha_changed (test_certification_replay_lifecycle.CertifierReplayIntegrationTests.test_recompute_rejects_current_identity_drift_even_if_registry_sha_changed) ... ok
test_missing_authority_field_fails_closed (test_certification_replay_lifecycle.ReplayAuthorityTests.test_missing_authority_field_fails_closed) ... ok
test_non_registry_score_change_still_fails_exact_replay (test_certification_replay_lifecycle.ReplayAuthorityTests.test_non_registry_score_change_still_fails_exact_replay) ... ok
test_primary_baseline_authority_drift_fails (test_certification_replay_lifecycle.ReplayAuthorityTests.test_primary_baseline_authority_drift_fails) ... ok
test_scored_identity_authority_drift_fails (test_certification_replay_lifecycle.ReplayAuthorityTests.test_scored_identity_authority_drift_fails) ... ok
test_whole_registry_sha_only_change_is_replay_equivalent (test_certification_replay_lifecycle.ReplayAuthorityTests.test_whole_registry_sha_only_change_is_replay_equivalent) ... ok
test_certificate_records_test_surface_glob (test_certified_test_surface.CertifiedTestSurfaceTests.test_certificate_records_test_surface_glob) ... ok
test_eol_policy_is_certified_and_required (test_certified_test_surface.CertifiedTestSurfaceTests.test_eol_policy_is_certified_and_required) ... ok
test_incomplete_eol_policy_is_rejected (test_certified_test_surface.CertifiedTestSurfaceTests.test_incomplete_eol_policy_is_rejected) ... ok
test_new_test_added_after_certification_fails_build_integrity (test_certified_test_surface.CertifiedTestSurfaceTests.test_new_test_added_after_certification_fails_build_integrity) ... ok
test_test_mutation_after_certification_fails_build_integrity (test_certified_test_surface.CertifiedTestSurfaceTests.test_test_mutation_after_certification_fails_build_integrity) ... ok
test_tests_are_part_of_certified_surface (test_certified_test_surface.CertifiedTestSurfaceTests.test_tests_are_part_of_certified_surface) ... ok
test_missing_applicable_dimension_blocks_certification (test_cold_audit_certification.ColdAuditChallengeTests.test_missing_applicable_dimension_blocks_certification) ... ok
test_non_numeric_row_still_exercises_atomicity_and_negation (test_cold_audit_certification.ColdAuditChallengeTests.test_non_numeric_row_still_exercises_atomicity_and_negation) ... ok
test_numeric_row_exercises_support_atomicity_negation_and_numeric (test_cold_audit_certification.ColdAuditChallengeTests.test_numeric_row_exercises_support_atomicity_negation_and_numeric) ... ok
test_one_error_in_one_dimension_blocks_certification (test_cold_audit_certification.ColdAuditChallengeTests.test_one_error_in_one_dimension_blocks_certification) ... ok
test_qualifier_and_relationship_dimensions_are_generated_when_applicable (test_cold_audit_certification.ColdAuditChallengeTests.test_qualifier_and_relationship_dimensions_are_generated_when_applicable) ... ok
test_semantic_freshness_ignores_rationale_receipt_and_request_noise (test_cold_audit_certification.ColdAuditChallengeTests.test_semantic_freshness_ignores_rationale_receipt_and_request_noise) ... ok
test_auditor_must_be_disjoint_from_all_gold_construction_groups (test_cold_audit_certification.ColdAuditGoldIndependenceTests.test_auditor_must_be_disjoint_from_all_gold_construction_groups) ... ok
test_missing_or_non_distinct_gold_lineage_fails_closed (test_cold_audit_certification.ColdAuditGoldIndependenceTests.test_missing_or_non_distinct_gold_lineage_fails_closed) ... ok
test_non_ollama_generic_command_remains_descriptive_not_certifiable (test_cold_audit_certification.ColdAuditProviderAuthorityTests.test_non_ollama_generic_command_remains_descriptive_not_certifiable) ... ok
test_ollama_operator_version_assertion_mismatch_fails (test_cold_audit_certification.ColdAuditProviderAuthorityTests.test_ollama_operator_version_assertion_mismatch_fails) ... ok
test_ollama_provider_uses_measured_digest_and_guarded_command (test_cold_audit_certification.ColdAuditProviderAuthorityTests.test_ollama_provider_uses_measured_digest_and_guarded_command) ... ok
test_certificate_carries_semantic_fingerprint_for_lifecycle_freshness (test_cold_audit_certification.ColdAuditRuntimeCertificationTests.test_certificate_carries_semantic_fingerprint_for_lifecycle_freshness) ... ok
test_cold_audit_key_is_architectural_w4_even_if_source_risk_is_w2 (test_cold_audit_certification.ColdAuditRuntimeCertificationTests.test_cold_audit_key_is_architectural_w4_even_if_source_risk_is_w2) ... ok
test_generated_certificate_is_runtime_source_version_and_coverage_bound (test_cold_audit_certification.ColdAuditRuntimeCertificationTests.test_generated_certificate_is_runtime_source_version_and_coverage_bound) ... ok
test_tampered_dimension_coverage_invalidates_runtime_authority (test_cold_audit_certification.ColdAuditRuntimeCertificationTests.test_tampered_dimension_coverage_invalidates_runtime_authority) ... ok
test_non_cp1252_unit_content_survives_the_command_bridge (test_cold_audit_semantic_and_providers.EchoBackendBridgeTests.test_non_cp1252_unit_content_survives_the_command_bridge) ... ok
test_wrapper_bridges_through_json_command_provider (test_cold_audit_semantic_and_providers.EchoBackendBridgeTests.test_wrapper_bridges_through_json_command_provider) ... ok
test_wrapper_cold_audit_role_roundtrip (test_cold_audit_semantic_and_providers.EchoBackendBridgeTests.test_wrapper_cold_audit_role_roundtrip) ... ok
test_ambiguous_normalized_match_rejected (test_cold_audit_semantic_and_providers.ProviderValidationTests.test_ambiguous_normalized_match_rejected) ... ok
test_exact_substring_passes (test_cold_audit_semantic_and_providers.ProviderValidationTests.test_exact_substring_passes) ... ok
test_fabricated_evidence_rejected (test_cold_audit_semantic_and_providers.ProviderValidationTests.test_fabricated_evidence_rejected) ... ok
test_json_extraction_handles_fences_and_think_blocks (test_cold_audit_semantic_and_providers.ProviderValidationTests.test_json_extraction_handles_fences_and_think_blocks) ... ok
test_trimmed_evidence_recovered (test_cold_audit_semantic_and_providers.ProviderValidationTests.test_trimmed_evidence_recovered) ... ok
test_whitespace_normalized_recovery_uses_source_bytes (test_cold_audit_semantic_and_providers.ProviderValidationTests.test_whitespace_normalized_recovery_uses_source_bytes) ... ok
test_auditor_crash_is_a_finding_not_a_crash (test_cold_audit_semantic_and_providers.SemanticColdAuditTests.test_auditor_crash_is_a_finding_not_a_crash) ... ok
test_empty_sample_cannot_pass (test_cold_audit_semantic_and_providers.SemanticColdAuditTests.test_empty_sample_cannot_pass) ... ok
test_independent_supportive_auditor_passes (test_cold_audit_semantic_and_providers.SemanticColdAuditTests.test_independent_supportive_auditor_passes) ... ok
test_same_family_auditor_cannot_pass_even_when_supportive (test_cold_audit_semantic_and_providers.SemanticColdAuditTests.test_same_family_auditor_cannot_pass_even_when_supportive) ... ok
test_unsupported_verdicts_become_bounded_disagreements (test_cold_audit_semantic_and_providers.SemanticColdAuditTests.test_unsupported_verdicts_become_bounded_disagreements) ... ok
test_adjudicator_failure_invalidates_entire_gold_build (test_gold_integrity.GoldConstructionIdentityTests.test_adjudicator_failure_invalidates_entire_gold_build) ... ok
test_gold_builders_require_three_empirical_distinct_groups (test_gold_integrity.GoldConstructionIdentityTests.test_gold_builders_require_three_empirical_distinct_groups) ... ok
test_declared_hash_must_equal_recomputed_content_hash (test_gold_integrity.GovernedGoldSourceTests.test_declared_hash_must_equal_recomputed_content_hash) ... ok
test_exact_content_is_rehashed_not_trusted_from_declared_hash (test_gold_integrity.GovernedGoldSourceTests.test_exact_content_is_rehashed_not_trusted_from_declared_hash) ... ok
test_missing_or_extra_units_cannot_receive_machines_benchmark_label (test_gold_integrity.GovernedGoldSourceTests.test_missing_or_extra_units_cannot_receive_machines_benchmark_label) ... ok
test_pdf_identity_must_match_pinned_machines_source (test_gold_integrity.GovernedGoldSourceTests.test_pdf_identity_must_match_pinned_machines_source) ... ok
test_disjoint_registered_empirical_family_can_be_scored (test_gold_integrity.ScoringContaminationTests.test_disjoint_registered_empirical_family_can_be_scored) ... ok
test_missing_gold_family_lineage_fails_closed (test_gold_integrity.ScoringContaminationTests.test_missing_gold_family_lineage_fails_closed) ... ok
test_mixed_candidate_worker_identities_fail_closed (test_gold_integrity.ScoringContaminationTests.test_mixed_candidate_worker_identities_fail_closed) ... ok
test_non_empirical_scored_model_is_rejected (test_gold_integrity.ScoringContaminationTests.test_non_empirical_scored_model_is_rejected) ... ok
test_same_family_different_model_alias_is_still_contaminated (test_gold_integrity.ScoringContaminationTests.test_same_family_different_model_alias_is_still_contaminated) ... ok
test_apply_refuses_unverified_legacy_score_json (test_gold_integrity.SourceBoundScoringAndCertificationTests.test_apply_refuses_unverified_legacy_score_json) ... score reports are not self-describing and no complete verification inputs were supplied
ok
test_cherry_picked_W2_scope_cannot_be_certified (test_gold_integrity.SourceBoundScoringAndCertificationTests.test_cherry_picked_W2_scope_cannot_be_certified) ... ok
test_fabricated_candidate_evidence_is_rejected_not_counted_as_fidelity (test_gold_integrity.SourceBoundScoringAndCertificationTests.test_fabricated_candidate_evidence_is_rejected_not_counted_as_fidelity) ... ok
test_hand_edited_score_report_fails_recomputation (test_gold_integrity.SourceBoundScoringAndCertificationTests.test_hand_edited_score_report_fails_recomputation) ... ok
test_self_describing_scores_are_auto_recomputed_by_certifier (test_gold_integrity.SourceBoundScoringAndCertificationTests.test_self_describing_scores_are_auto_recomputed_by_certifier) ... ok
test_source_units_are_inferred_from_run_candidate_path (test_gold_integrity.SourceBoundScoringAndCertificationTests.test_source_units_are_inferred_from_run_candidate_path) ... ok
test_tampered_gold_raw_artifact_breaks_score (test_gold_integrity.SourceBoundScoringAndCertificationTests.test_tampered_gold_raw_artifact_breaks_score) ... ok
test_mac_value_does_not_contradict_mac_reduction (test_hardening_regressions.ComparatorSafetyTests.test_mac_value_does_not_contradict_mac_reduction) ... ok
test_partial_pressure_does_not_contradict_partial_laryngectomy (test_hardening_regressions.ComparatorSafetyTests.test_partial_pressure_does_not_contradict_partial_laryngectomy) ... ok
test_build_failure_stops_before_any_provider_call (test_hardening_regressions.PredispatchTests.test_build_failure_stops_before_any_provider_call) ... ok
test_hard_failure_dominates_external_blocker (test_hardening_regressions.ReadinessTests.test_hard_failure_dominates_external_blocker) ... ok
test_bad_page_range (test_ingest_network.PageSpecTests.test_bad_page_range) ... ok
test_page_ranges (test_ingest_network.PageSpecTests.test_page_ranges) ... ok
test_machines_three_page_ingestion_if_source_available (test_ingest_network.RealPdfIngestionTests.test_machines_three_page_ingestion_if_source_available) ... skipped 'Machines source not mounted'
test_added_production_file_detected (test_integrity_readiness.BuildIntegrityTests.test_added_production_file_detected) ... ok
test_certified_build_detects_mutation_and_verify_does_not_recertify (test_integrity_readiness.BuildIntegrityTests.test_certified_build_detects_mutation_and_verify_does_not_recertify) ... ok
test_validation_harness_mutation_invalidates_certification (test_integrity_readiness.BuildIntegrityTests.test_validation_harness_mutation_invalidates_certification) ... ok
test_package_roundtrip (test_integrity_readiness.PackageTests.test_package_roundtrip) ... ok
test_package_status_cannot_override_readiness (test_integrity_readiness.PackageTests.test_package_status_cannot_override_readiness) ... ok
test_read_only_bridge_blocks_write (test_integrity_readiness.ReadOnly09DTests.test_read_only_bridge_blocks_write) ... ok
test_bounded_review_queue_can_be_frontier_review_ready (test_integrity_readiness.ReadinessTests.test_bounded_review_queue_can_be_frontier_review_ready) ... ok
test_external_provider_block_yields_ready_for_provider (test_integrity_readiness.ReadinessTests.test_external_provider_block_yields_ready_for_provider) ... ok
test_not_run_cannot_be_ready (test_integrity_readiness.ReadinessTests.test_not_run_cannot_be_ready) ... ok
test_unbounded_review_failure_blocks (test_integrity_readiness.ReadinessTests.test_unbounded_review_failure_blocks) ... ok
test_runtime_lock_mutation_fails (test_integrity_readiness.RuntimeLockTests.test_runtime_lock_mutation_fails) ... ok
test_runtime_lock_roundtrip (test_integrity_readiness.RuntimeLockTests.test_runtime_lock_roundtrip) ... ok
test_atomic_commit_and_reconciliation (test_ledger_staging.LedgerTests.test_atomic_commit_and_reconciliation) ... ok
test_duplicate_active_lease_rejected (test_ledger_staging.LedgerTests.test_duplicate_active_lease_rejected) ... ok
test_event_tamper_detected (test_ledger_staging.LedgerTests.test_event_tamper_detected) ... ok
test_expired_lease_requeues (test_ledger_staging.LedgerTests.test_expired_lease_requeues) ... ok
test_illegal_direct_accept_rejected (test_ledger_staging.LedgerTests.test_illegal_direct_accept_rejected) ... ok
test_old_worker_after_expiry_rejected (test_ledger_staging.LedgerTests.test_old_worker_after_expiry_rejected) ... ok
test_register_becomes_ready (test_ledger_staging.LedgerTests.test_register_becomes_ready) ... ok
test_restart_reconstructs (test_ledger_staging.LedgerTests.test_restart_reconstructs) ... ok
test_stale_commit_rejected (test_ledger_staging.LedgerTests.test_stale_commit_rejected) ... ok
test_state_table_tamper_detected (test_ledger_staging.LedgerTests.test_state_table_tamper_detected) ... ok
test_two_controllers_race_one_lease_wins (test_ledger_staging.LedgerTests.test_two_controllers_race_one_lease_wins) ... ok
test_complete_stage_verifies (test_ledger_staging.StagingTests.test_complete_stage_verifies) ... ok
test_post_stage_artifact_mutation_fails (test_ledger_staging.StagingTests.test_post_stage_artifact_mutation_fails) ... ok
test_torn_stage_missing_completion_fails (test_ledger_staging.StagingTests.test_torn_stage_missing_completion_fails) ... ok
test_absent_registry_entry_is_unbenchmarked (test_model_registry.RegistryAuthorityTests.test_absent_registry_entry_is_unbenchmarked) ... ok
test_only_registry_status_controls_certification (test_model_registry.RegistryAuthorityTests.test_only_registry_status_controls_certification) ... ok
test_blank_independence_group_is_rejected (test_model_registry_strictness.ModelRegistryStrictnessTests.test_blank_independence_group_is_rejected) ... ok
test_complete_identity_resolves (test_model_registry_strictness.ModelRegistryStrictnessTests.test_complete_identity_resolves) ... ok
test_missing_empirical_status_does_not_default_true (test_model_registry_strictness.ModelRegistryStrictnessTests.test_missing_empirical_status_does_not_default_true) ... ok
test_missing_independence_group_does_not_fallback_to_family (test_model_registry_strictness.ModelRegistryStrictnessTests.test_missing_independence_group_does_not_fallback_to_family) ... ok
test_non_boolean_empirical_status_is_rejected (test_model_registry_strictness.ModelRegistryStrictnessTests.test_non_boolean_empirical_status_is_rejected) ... ok
test_observed_version_policy_cannot_be_blank (test_model_registry_strictness.ModelRegistryStrictnessTests.test_observed_version_policy_cannot_be_blank) ... ok
test_registry_identity_container_must_be_object (test_model_registry_strictness.ModelRegistryStrictnessTests.test_registry_identity_container_must_be_object) ... ok
test_certifiable_version_preserves_metrics_status (test_model_version_binding.CertificationVersionGateTests.test_certifiable_version_preserves_metrics_status) ... ok
test_metrics_pass_becomes_blocked_external_when_version_unpinned (test_model_version_binding.CertificationVersionGateTests.test_metrics_pass_becomes_blocked_external_when_version_unpinned) ... ok
test_malformed_digest_fails_closed (test_model_version_binding.OllamaDigestDiscoveryTests.test_malformed_digest_fails_closed) ... ok
test_missing_or_ambiguous_model_fails_closed (test_model_version_binding.OllamaDigestDiscoveryTests.test_missing_or_ambiguous_model_fails_closed) ... ok
test_operator_cannot_spoof_ollama_version (test_model_version_binding.OllamaDigestDiscoveryTests.test_operator_cannot_spoof_ollama_version) ... ok
test_provider_flags_bind_digest_guard_and_same_host (test_model_version_binding.OllamaDigestDiscoveryTests.test_provider_flags_bind_digest_guard_and_same_host) ... ok
test_resolves_digest_from_same_ollama_host (test_model_version_binding.OllamaDigestDiscoveryTests.test_resolves_digest_from_same_ollama_host) ... ok
test_post_call_digest_mismatch_discards_successful_semantic_output (test_model_version_binding.OllamaSemanticGuardTests.test_post_call_digest_mismatch_discards_successful_semantic_output) ... ok
test_pre_call_digest_mismatch_prevents_semantic_process_start (test_model_version_binding.OllamaSemanticGuardTests.test_pre_call_digest_mismatch_prevents_semantic_process_start) ... ok
test_stable_before_after_digest_releases_provider_json_with_receipt (test_model_version_binding.OllamaSemanticGuardTests.test_stable_before_after_digest_releases_provider_json_with_receipt) ... ok
test_same_alias_mixed_observed_versions_is_rejected (test_model_version_binding.ScorerVersionIdentityTests.test_same_alias_mixed_observed_versions_is_rejected) ... ok
test_scored_identity_carries_observed_digest (test_model_version_binding.ScorerVersionIdentityTests.test_scored_identity_carries_observed_digest) ... ok
test_generic_cli_observed_policy_is_never_certification_authority (test_model_version_binding.VersionPolicyTests.test_generic_cli_observed_policy_is_never_certification_authority) ... ok
test_ollama_digest_is_certifiable (test_model_version_binding.VersionPolicyTests.test_ollama_digest_is_certifiable) ... ok
test_ollama_placeholder_is_not_certifiable (test_model_version_binding.VersionPolicyTests.test_ollama_placeholder_is_not_certifiable) ... ok
test_unpinned_hosted_alias_is_not_certifiable (test_model_version_binding.VersionPolicyTests.test_unpinned_hosted_alias_is_not_certifiable) ... ok
test_contradiction_queue_rejects_unstructured_contradiction (test_owner_real_validation.OwnerValidationHelperTests.test_contradiction_queue_rejects_unstructured_contradiction) ... ok
test_gold_reference_must_match_source_and_reference_hash (test_owner_real_validation.OwnerValidationHelperTests.test_gold_reference_must_match_source_and_reference_hash) ... ok
test_gold_scoring_disjointness_passes_for_separate_families (test_owner_real_validation.OwnerValidationHelperTests.test_gold_scoring_disjointness_passes_for_separate_families) ... ok
test_gold_scoring_family_overlap_is_rejected_even_with_different_model_alias (test_owner_real_validation.OwnerValidationHelperTests.test_gold_scoring_family_overlap_is_rejected_even_with_different_model_alias) ... ok
test_independence_requires_distinct_empirical_groups (test_owner_real_validation.OwnerValidationHelperTests.test_independence_requires_distinct_empirical_groups) ... ok
test_non_empirical_provider_is_rejected (test_owner_real_validation.OwnerValidationHelperTests.test_non_empirical_provider_is_rejected) ... ok
test_parse_spec_preserves_ollama_tag (test_owner_real_validation.OwnerValidationHelperTests.test_parse_spec_preserves_ollama_tag) ... ok
test_content_tamper_is_rejected (test_package_security.PackageSecurityTests.test_content_tamper_is_rejected) ... ok
test_duplicate_archive_member_is_rejected (test_package_security.PackageSecurityTests.test_duplicate_archive_member_is_rejected) ... C:\Users\sethb\.local\python\project09d-cpython-3.12.13\Lib\zipfile\__init__.py:1624: UserWarning: Duplicate name: 'RUN/x.txt'
  return self._open_to_write(zinfo, force_zip64=force_zip64)
ok
test_path_traversal_member_is_rejected_before_extraction (test_package_security.PackageSecurityTests.test_path_traversal_member_is_rejected_before_extraction) ... ok
test_top_level_extra_file_is_rejected (test_package_security.PackageSecurityTests.test_top_level_extra_file_is_rejected) ... ok
test_table_numeric_candidate_is_prioritized_without_increasing_sample_volume (test_pipeline_optimization.ColdAuditSamplingTests.test_table_numeric_candidate_is_prioritized_without_increasing_sample_volume) ... ok
test_keep_alive_and_deterministic_temperature_are_sent (test_pipeline_optimization.OllamaResidencyTests.test_keep_alive_and_deterministic_temperature_are_sent) ... ok
test_auto_keeps_remote_models_parallel (test_pipeline_optimization.SchedulerTests.test_auto_keeps_remote_models_parallel) ... ok
test_auto_phases_distinct_local_models (test_pipeline_optimization.SchedulerTests.test_auto_phases_distinct_local_models) ... ok
test_local_default_concurrency_is_one_but_override_is_honored (test_pipeline_optimization.SchedulerTests.test_local_default_concurrency_is_one_but_override_is_honored) ... ok
test_json_stdin_stdout_provider (test_provider_and_pipeline.CommandProviderTests.test_json_stdin_stdout_provider) ... ok
test_cloud_mode_allows_network_provider (test_provider_and_pipeline.NetworkPolicyTests.test_cloud_mode_allows_network_provider) ... ok
test_local_only_rejects_network_provider (test_provider_and_pipeline.NetworkPolicyTests.test_local_only_rejects_network_provider) ... ok
test_one_unit_fixture_pipeline_outputs_package_and_blocks_semantic_certification (test_provider_and_pipeline.PipelineTests.test_one_unit_fixture_pipeline_outputs_package_and_blocks_semantic_certification) ... ok
test_missing_witness_constraint_fails_closed (test_reconciliation_v14_harvest.ContractTests.test_missing_witness_constraint_fails_closed) ... ok
test_structural_contract_passes_readonly (test_reconciliation_v14_harvest.ContractTests.test_structural_contract_passes_readonly) ... ok
test_old_artifact_defaults_are_not_overwritten_with_none (test_reconciliation_v14_harvest.IdentityTests.test_old_artifact_defaults_are_not_overwritten_with_none) ... ok
test_stable_identity_survives_run_id_change (test_reconciliation_v14_harvest.IdentityTests.test_stable_identity_survives_run_id_change) ... ok
test_invalid_09d_contract_blocks_before_provider_execution (test_reconciliation_v14_harvest.PredispatchTests.test_invalid_09d_contract_blocks_before_provider_execution) ... ok
test_atomic_json_replaces_without_temp_residue (test_reconciliation_v14_harvest.SafetyTests.test_atomic_json_replaces_without_temp_residue) ... ok
test_atomic_json_retries_transient_windows_replace_lock (test_reconciliation_v14_harvest.SafetyTests.test_atomic_json_retries_transient_windows_replace_lock) ... ok
test_lease_ttl_outlives_provider_timeout (test_reconciliation_v14_harvest.SafetyTests.test_lease_ttl_outlives_provider_timeout) ... ok
test_requested_poststage_failure_downgrades_status (test_reconciliation_v14_harvest.SafetyTests.test_requested_poststage_failure_downgrades_status) ... ok
test_terminal_json_parser_ignores_prior_braces (test_reconciliation_v14_harvest.SafetyTests.test_terminal_json_parser_ignores_prior_braces) ... ok
test_cold_audit_uses_independence_group_not_family_label (test_runtime_independence_groups.ColdAuditGroupTests.test_cold_audit_uses_independence_group_not_family_label) ... ok
test_same_group_is_rejected_before_any_real_provider_call (test_runtime_independence_groups.PredispatchTopologyTests.test_same_group_is_rejected_before_any_real_provider_call) ... ok
test_cold_auditor_cannot_share_primary_group (test_runtime_independence_groups.RuntimeTopologyTests.test_cold_auditor_cannot_share_primary_group) ... ok
test_distinct_family_labels_same_group_are_not_independent (test_runtime_independence_groups.RuntimeTopologyTests.test_distinct_family_labels_same_group_are_not_independent) ... ok
test_provider_empirical_self_claim_cannot_override_registry (test_runtime_independence_groups.RuntimeTopologyTests.test_provider_empirical_self_claim_cannot_override_registry) ... ok
test_provider_family_spoof_is_rejected (test_runtime_independence_groups.RuntimeTopologyTests.test_provider_family_spoof_is_rejected) ... ok
test_bound_digest_accepts_exact_scored_candidate_bytes (test_semantic_digest_binding.SemanticDigestByteBindingTests.test_bound_digest_accepts_exact_scored_candidate_bytes) ... ok
test_post_score_candidate_mutation_is_refused (test_semantic_digest_binding.SemanticDigestByteBindingTests.test_post_score_candidate_mutation_is_refused) ... ok
test_evidence_change_is_new_semantic_evidence (test_semantic_freshness.CandidateSemanticDigestTests.test_evidence_change_is_new_semantic_evidence) ... ok
test_metadata_ids_lineage_and_order_do_not_manufacture_freshness (test_semantic_freshness.CandidateSemanticDigestTests.test_metadata_ids_lineage_and_order_do_not_manufacture_freshness) ... ok
test_observed_model_version_change_is_new_semantic_identity (test_semantic_freshness.CandidateSemanticDigestTests.test_observed_model_version_change_is_new_semantic_identity) ... ok
test_out_of_scope_metadata_or_semantics_do_not_change_certified_scope_digest (test_semantic_freshness.CandidateSemanticDigestTests.test_out_of_scope_metadata_or_semantics_do_not_change_certified_scope_digest) ... ok
test_proposition_change_is_new_semantic_evidence (test_semantic_freshness.CandidateSemanticDigestTests.test_proposition_change_is_new_semantic_evidence) ... ok
test_blind_semantic_fingerprint_binds_primary_semantic_baseline (test_semantic_freshness.SemanticLifecycleFreshnessTests.test_blind_semantic_fingerprint_binds_primary_semantic_baseline) ... ok
test_changed_semantic_digest_can_reactivate_nonretired_role (test_semantic_freshness.SemanticLifecycleFreshnessTests.test_changed_semantic_digest_can_reactivate_nonretired_role) ... ok
test_lifecycle_prefers_semantic_fingerprint (test_semantic_freshness.SemanticLifecycleFreshnessTests.test_lifecycle_prefers_semantic_fingerprint) ... ok
test_metadata_only_file_hash_change_cannot_reactivate_same_semantics (test_semantic_freshness.SemanticLifecycleFreshnessTests.test_metadata_only_file_hash_change_cannot_reactivate_same_semantics) ... ok
test_current_registry_identity_drift_invalidates_certificate (test_sourcebound_certification.SourceBoundCertificationTests.test_current_registry_identity_drift_invalidates_certificate) ... ok
test_exact_verified_source_scope_version_and_authority_pass (test_sourcebound_certification.SourceBoundCertificationTests.test_exact_verified_source_scope_version_and_authority_pass) ... ok
test_malformed_certifications_container_fails_closed (test_sourcebound_certification.SourceBoundCertificationTests.test_malformed_certifications_container_fails_closed) ... ok
test_missing_authority_projection_fails_closed (test_sourcebound_certification.SourceBoundCertificationTests.test_missing_authority_projection_fails_closed) ... ok
test_missing_certified_model_version_fails (test_sourcebound_certification.SourceBoundCertificationTests.test_missing_certified_model_version_fails) ... ok
test_missing_evidence_chain_hash_fails (test_sourcebound_certification.SourceBoundCertificationTests.test_missing_evidence_chain_hash_fails) ... ok
test_placeholder_certified_model_version_fails (test_sourcebound_certification.SourceBoundCertificationTests.test_placeholder_certified_model_version_fails) ... ok
test_projection_identity_must_match_certificate_identity (test_sourcebound_certification.SourceBoundCertificationTests.test_projection_identity_must_match_certificate_identity) ... ok
test_rejected_status_fails (test_sourcebound_certification.SourceBoundCertificationTests.test_rejected_status_fails) ... ok
test_same_alias_new_model_digest_does_not_inherit_certification (test_sourcebound_certification.SourceBoundCertificationTests.test_same_alias_new_model_digest_does_not_inherit_certification) ... ok
test_same_class_different_source_artifact_does_not_inherit_certification (test_sourcebound_certification.SourceBoundCertificationTests.test_same_class_different_source_artifact_does_not_inherit_certification) ... ok
test_scored_model_identity_mismatch_fails (test_sourcebound_certification.SourceBoundCertificationTests.test_scored_model_identity_mismatch_fails) ... ok
test_tampered_authority_projection_hash_fails_closed (test_sourcebound_certification.SourceBoundCertificationTests.test_tampered_authority_projection_hash_fails_closed) ... ok
test_unit_outside_certified_scope_fails (test_sourcebound_certification.SourceBoundCertificationTests.test_unit_outside_certified_scope_fails) ... ok
test_unrelated_registry_certification_does_not_invalidate_certificate (test_sourcebound_certification.SourceBoundCertificationTests.test_unrelated_registry_certification_does_not_invalidate_certificate) ... ok
test_unverified_benchmark_inputs_fail (test_sourcebound_certification.SourceBoundCertificationTests.test_unverified_benchmark_inputs_fail) ... ok
test_other_active_certificate_keeps_role_aggregate_certified (test_stale_recertification.AggregateRoleStatusTests.test_other_active_certificate_keeps_role_aggregate_certified) ... ok
test_blind_fingerprint_binds_primary_baseline_candidate_file (test_stale_recertification.EvidenceFingerprintTests.test_blind_fingerprint_binds_primary_baseline_candidate_file) ... ok
test_exact_stale_evidence_cannot_restore_authority (test_stale_recertification.EvidenceFingerprintTests.test_exact_stale_evidence_cannot_restore_authority) ... ok
test_invalidated_evidence_deduplicates_across_downward_transitions (test_stale_recertification.EvidenceFingerprintTests.test_invalidated_evidence_deduplicates_across_downward_transitions) ... ok
test_legacy_blind_without_primary_baseline_uses_fallback_and_is_still_blocked (test_stale_recertification.EvidenceFingerprintTests.test_legacy_blind_without_primary_baseline_uses_fallback_and_is_still_blocked) ... ok
test_lifecycle_records_invalidated_evidence (test_stale_recertification.EvidenceFingerprintTests.test_lifecycle_records_invalidated_evidence) ... ok
test_new_candidate_evidence_can_reactivate_nonretired_role (test_stale_recertification.EvidenceFingerprintTests.test_new_candidate_evidence_can_reactivate_nonretired_role) ... ok
test_retired_key_blocks_even_fresh_evidence (test_stale_recertification.EvidenceFingerprintTests.test_retired_key_blocks_even_fresh_evidence) ... ok
test_conflicting_source_risk_metadata_is_p0 (test_w3_tierb_routing.W3TierBRoutingTests.test_conflicting_source_risk_metadata_is_p0) ... ok
test_primary_request_remains_w2_candidate_generation_for_w3_equation_source (test_w3_tierb_routing.W3TierBRoutingTests.test_primary_request_remains_w2_candidate_generation_for_w3_equation_source) ... ok
test_w2_text_family_can_still_be_locally_complete_when_no_other_flags_exist (test_w3_tierb_routing.W3TierBRoutingTests.test_w2_text_family_can_still_be_locally_complete_when_no_other_flags_exist) ... ok
test_w3_equation_family_cannot_be_locally_closed_without_any_specialist_flags (test_w3_tierb_routing.W3TierBRoutingTests.test_w3_equation_family_cannot_be_locally_closed_without_any_specialist_flags) ... ok

----------------------------------------------------------------------
Ran 262 tests in 7.719s

OK (skipped=1)
```
