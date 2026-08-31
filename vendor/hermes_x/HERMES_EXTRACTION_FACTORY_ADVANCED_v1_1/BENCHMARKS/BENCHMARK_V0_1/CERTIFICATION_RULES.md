# Provisional Certification Rules

These thresholds are experimental until real results exist.

CERT-W1:
- recall >= .98
- precision >= .98
- no material invented source tokens

CERT-W2-S0:
- recall >= .92
- precision >= .92
- evidence fidelity = 1.00 on accepted ordinary text claims
- E4 = 0
- E3 <= .5%
- atomicity failure <= 5%

CERT-W2-S1:
- recall >= .94
- precision >= .93
- evidence fidelity = 1.00
- E4 = 0
- E3 <= .5%
- qualifier preservation >= .95 where applicable

CERT-BLIND-RECALL:
- >=50% seeded omission recovery
- useful-new-candidate precision >= .70
- E4 = 0

CERT-W3-ASSIST:
- binding/repair accuracy >= .95
- harmful repair <=1%
- E4 = 0
- appropriate defer >= .90

No W3/W4 autonomous closure is granted to Tier A.
