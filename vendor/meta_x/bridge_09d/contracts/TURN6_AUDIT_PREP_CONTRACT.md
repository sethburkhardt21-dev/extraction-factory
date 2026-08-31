# Turn 6 Audit Preparation Contract — v1.0

The Turn-6 factory composes:

```text
primary assertions
+ append-only verifier events
        ↓
provisional source-mention candidates
        ↓
read-only 09D identity lookup
        ↓
read-only assertion comparison
```

It may generate audit evidence and proposed target IDs. It may not assign canonical identity, mutate 09D, merge candidates, promote candidates, select a conflicting value, or authorize generation/public use.

High-risk but independently entailed assertions may be compared read-only even while frontier adjudication remains required for downstream use.
