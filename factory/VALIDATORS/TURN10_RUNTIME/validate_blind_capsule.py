from pathlib import Path
import json, sys

FORBIDDEN_NAMES={
    "primary_candidates.jsonl","candidates.jsonl","reference_answers.jsonl",
    "gold.jsonl","answer_key.json","answer_key.jsonl"
}

def validate_capsule(path):
    path=Path(path)
    m=json.loads((path/"CAPSULE_MANIFEST.json").read_text(encoding="utf-8"))
    blind=m.get("blindness_class","")
    if blind not in ("BLIND_SOURCE_ONLY","BLIND_STRUCTURED_INPUT"):
        return []
    errors=[]
    for p in path.rglob("*"):
        if not p.is_file(): continue
        rel=str(p.relative_to(path)).lower()
        if p.name.lower() in FORBIDDEN_NAMES:
            errors.append(f"forbidden_file:{rel}")
        if "answer_key" in rel or "/gold/" in "/"+rel or "reference_answer" in rel:
            errors.append(f"forbidden_path:{rel}")
    return sorted(set(errors))

if __name__=="__main__":
    errs=validate_capsule(sys.argv[1])
    if errs:
        print("BLINDNESS INPUT VALIDATION: FAIL")
        for e in errs: print(e)
        raise SystemExit(1)
    print("BLINDNESS INPUT VALIDATION: PASS")
