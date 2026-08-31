# EXP-007 — Gold Leakage / Circularity Audit
Status: REQUIRED

Validate that historical extraction outputs do not define the benchmark answer key.

Core test:
build Reference v1 from source-only gold workers;
reveal historical outputs afterward;
measure historical-only additions and adjudicate them from source.
