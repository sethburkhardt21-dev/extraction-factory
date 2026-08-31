import json, sys
from pathlib import Path
ALLOWED={"LOGICAL_SCHEMA","EXTENSION_FIELD","PROCESS_METADATA","QUARANTINE","EXPLICIT_DROP"}
d=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
errors=[]; seen=set()
for x in d.get("fields",[]):
    f=x.get("produced_field")
    if not f or f in seen: errors.append(f"duplicate_or_missing_field:{f}")
    seen.add(f)
    if x.get("disposition") not in ALLOWED: errors.append(f"bad_disposition:{f}")
    if x.get("disposition")=="EXPLICIT_DROP" and not x.get("drop_reason"): errors.append(f"missing_drop_reason:{f}")
    if x.get("disposition")!="EXPLICIT_DROP" and not x.get("target"): errors.append(f"missing_target:{f}")
if errors:
    print("SCHEMA COVERAGE: FAIL"); [print(e) for e in errors]; raise SystemExit(1)
print("SCHEMA COVERAGE: PASS")
