# Factory Implementation Maturity Matrix v0.1

| Component | Design | Code | Tests | Real source | Production | Blocker | Next proof |
|---|---|---|---|---|---|---|---|
| source_identity | OFFLINE_CERTIFIED | OFFLINE_CERTIFIED | OFFLINE_CERTIFIED | OFFLINE_CERTIFIED | EXPERIMENTAL | Need broader source-set checks | Verify all frozen estates |
| page_artifacts | OFFLINE_CERTIFIED | OFFLINE_CERTIFIED | OFFLINE_CERTIFIED | OFFLINE_CERTIFIED | EXPERIMENTAL | Implemented for Machines pilot only | Generalize generator |
| source_units | OFFLINE_CERTIFIED | OFFLINE_CERTIFIED | OFFLINE_CERTIFIED | OFFLINE_CERTIFIED | EXPERIMENTAL | Pilot segmentation only | Run segmentation benchmark across strata |
| capsule_generator | OFFLINE_CERTIFIED | SKELETON_ONLY | OFFLINE_CERTIFIED | OFFLINE_CERTIFIED | EXPERIMENTAL | Pilot generator only | Generalize to estate scheduler |
| risk_classifier | OFFLINE_CERTIFIED | SKELETON_ONLY | IMPLEMENTED_UNTESTED | NOT_IMPLEMENTED | EXPERIMENTAL | Threshold calibration absent | Run EXP-003 |
| primary_worker_adapter | OFFLINE_CERTIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | BLOCKED | No Hermes/provider adapter executed | Implement provider adapter |
| blind_recall_adapter | OFFLINE_CERTIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | BLOCKED | No live worker execution | Implement and benchmark |
| numeric_literal_pass | OFFLINE_CERTIFIED | SKELETON_ONLY | IMPLEMENTED_UNTESTED | NOT_IMPLEMENTED | EXPERIMENTAL | Prompt/contract only | Execute pilot |
| numeric_binding_pass | OFFLINE_CERTIFIED | SKELETON_ONLY | IMPLEMENTED_UNTESTED | NOT_IMPLEMENTED | BLOCKED | Tier-B model not certified | Benchmark W3 |
| qualifier_pass | OFFLINE_CERTIFIED | SKELETON_ONLY | IMPLEMENTED_UNTESTED | NOT_IMPLEMENTED | EXPERIMENTAL | Prompt/contract only | Execute pilot |
| relationship_pass | OFFLINE_CERTIFIED | SKELETON_ONLY | IMPLEMENTED_UNTESTED | NOT_IMPLEMENTED | EXPERIMENTAL | No pilot execution | Execute relationship challenge |
| visual_pass | OFFLINE_CERTIFIED | SKELETON_ONLY | IMPLEMENTED_UNTESTED | OFFLINE_CERTIFIED | EXPERIMENTAL | Assets packaged, no model run | Run multimodal worker |
| deterministic_union | OFFLINE_CERTIFIED | SKELETON_ONLY | OFFLINE_CERTIFIED | NOT_IMPLEMENTED | EXPERIMENTAL | No real multi-worker outputs yet | Union pilot outputs |
| evidence_family_builder | OFFLINE_CERTIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | BLOCKED | Requires real outputs | Implement after pilot |
| precision_reviewer | OFFLINE_CERTIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | BLOCKED | No certified Tier-B worker | Benchmark/adapter |
| escalation_router | OFFLINE_CERTIFIED | SKELETON_ONLY | IMPLEMENTED_UNTESTED | NOT_IMPLEMENTED | EXPERIMENTAL | Thresholds uncalibrated | Run EXP-013 |
| worker_leases | OFFLINE_CERTIFIED | SKELETON_ONLY | IMPLEMENTED_UNTESTED | NOT_IMPLEMENTED | EXPERIMENTAL | Schema only | Implement scheduler |
| durable_ledger | OFFLINE_CERTIFIED | SKELETON_ONLY | IMPLEMENTED_UNTESTED | NOT_IMPLEMENTED | EXPERIMENTAL | Backend not selected | Turn10 implementation decision |
| scheduler | OFFLINE_CERTIFIED | SKELETON_ONLY | IMPLEMENTED_UNTESTED | NOT_IMPLEMENTED | BLOCKED | Pseudocode only | Implement minimal local scheduler |
| provider_adapters | OFFLINE_CERTIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | BLOCKED | No runtime adapters | Implement Hermes bridge |
| buzz_bridge | OFFLINE_CERTIFIED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | BLOCKED | Native launch mode unverified | Run sidecar/native pilot |
| validators | OFFLINE_CERTIFIED | SKELETON_ONLY | OFFLINE_CERTIFIED | OFFLINE_CERTIFIED | EXPERIMENTAL | Limited reference implementation | Expand against real estates |
| mutation_tests | OFFLINE_CERTIFIED | SKELETON_ONLY | OFFLINE_CERTIFIED | OFFLINE_CERTIFIED | EXPERIMENTAL | Semantic mutations not fully executable | Add real-source canaries |
| cold_audit_sampler | OFFLINE_CERTIFIED | SKELETON_ONLY | IMPLEMENTED_UNTESTED | NOT_IMPLEMENTED | EXPERIMENTAL | Sampling rate uncalibrated | Run EXP-024 |
| package_builder | OFFLINE_CERTIFIED | SKELETON_ONLY | OFFLINE_CERTIFIED | OFFLINE_CERTIFIED | EXPERIMENTAL | Pilot-only packaging | Generalize |
| preflight | OFFLINE_CERTIFIED | OFFLINE_CERTIFIED | OFFLINE_CERTIFIED | OFFLINE_CERTIFIED | EXPERIMENTAL | Reference-pack scope only | Run against real estate package |
| benchmark_harness | OFFLINE_CERTIFIED | SKELETON_ONLY | IMPLEMENTED_UNTESTED | NOT_IMPLEMENTED | BLOCKED | 48-unit corpus not built | Build/run benchmark |
| model_certification_registry | OFFLINE_CERTIFIED | SKELETON_ONLY | IMPLEMENTED_UNTESTED | NOT_IMPLEMENTED | BLOCKED | No model certified | Run benchmark |
| 09d_audit_bridge | OFFLINE_CERTIFIED | SKELETON_ONLY | IMPLEMENTED_UNTESTED | NOT_IMPLEMENTED | EXPERIMENTAL | Projection contract only | Map real package to 09D audit intake |
