# W2 Primary Extraction — Blind Benchmark Prompt

You receive only the governed source unit and schema.

Extract all explicit, source-supported, clinically meaningful atomic propositions in the assigned source unit.

Rules:
- no outside medical knowledge;
- preserve exact evidence;
- preserve qualifiers, negation, timing, population, exceptions;
- split independent clauses when they can stand alone;
- do not convert a visual implication into text evidence unless the visual was provided;
- do not target a candidate count;
- mark uncertainty/defer rather than invent context;
- every output remains UNREVIEWED / NON-CANONICAL.

Do not claim completeness.
