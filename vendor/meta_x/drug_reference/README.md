# Repaired DrugBank + RxNorm + LiverTox ingestion

This package removes the unsafe behavior in the supplied Meta engine:

- **no fabricated RxCUIs** (`hash(name)` is never used as an identifier);
- **no placeholder LiverTox likelihood or injury-pattern values** in production output;
- no silent demo DrugBank fallback;
- DrugBank XML is streamed with `iterparse` instead of loading the full document tree;
- RxNorm resolution uses the official RxNav response and distinguishes unique / none / ambiguous results;
- LiverTox input must carry source provenance;
- normalized-name cross-source linking is explicitly labeled and refuses ambiguous matches.

The user must provide a DrugBank XML artifact they are authorized to use. LiverTox structured capture remains a separate provenance-producing extraction step; this repaired core intentionally fails closed instead of inventing clinical attributes.
