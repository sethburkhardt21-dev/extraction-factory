"""Real semantic provider command for the Hermes JSONCommandProvider bridge.

Contract (hermes_factory.providers.command.JSONCommandProvider):
  stdin:  one JSON worker request (hermes-worker-request-1.1)
  stdout: one JSON provider response (hermes-semantic-provider-1.1)
  exit 0 on success; nonzero only on hard provider failure.

Backends:
  claude  — Anthropic Claude via the local `claude` CLI (non-interactive -p).
  ollama  — any local Ollama model via the localhost HTTP API.
  echo    — deterministic sentence splitter for wrapper self-tests only
            (mirrors the fixture provider; never an empirical claim).

The wrapper enforces the factory's hard evidence rule BEFORE emitting:
every assertion's `evidence` must be an exact contiguous substring of the
source-unit content. Assertions that fail after whitespace-exact recovery
are dropped into provider_diagnostics.rejected — never silently repaired
into something the model did not say, and never allowed to abort the unit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.request

MAX_ASSERTIONS_PER_UNIT = 60

RESPONSE_SCHEMA_HINT = """Return ONLY one JSON object, no markdown fences, no commentary:
{"assertions": [
  {"proposition": str,            // atomic restatement; see preservation rules
   "evidence": str,               // EXACT contiguous verbatim substring of CONTENT
   "subject": str|null,
   "predicate": str|null,
   "object_value": str|null,
   "numeric_values": [{"value_literal": str, "unit_literal": str|null}],
   "qualifiers": [str],
   "polarity": "AFFIRMATIVE"|"NEGATIVE",
   "certainty": "ASSERTED"|"HEDGED",
   "conditionality": str|null,
   "temporality": str|null,
   "comparison": str|null,
   "relationship_direction": "INCREASES"|"DECREASES"|"DEPENDS_ON"|"UNAFFECTED_BY"|"EQUALS"|"CAUSES"|"RELATED_TO"|null,
   "uncertainty_flags": [str]}
]}"""

PRESERVATION_RULES = """HARD RULES:
1. `evidence` must be copied verbatim from CONTENT — exact characters, casing,
   punctuation, internal spacing. Prefer one complete sentence per assertion.
2. The `proposition` must preserve VERBATIM every item that appears in its
   evidence span: every number with its unit (e.g. "760 mm Hg", "20°C"),
   every qualifier cue word (not, no, neither, nor, without, never, except,
   unless, only, may, might, can, could, should, must, if, when, usually,
   often, commonly, rarely, sometimes, always, more, less, greater, lower,
   higher, before, after, during, while, until), and every relationship cue
   (increases, decreases, raises, lowers, reduces, depends on, unaffected by,
   equals, causes, results in, leads to, associated with).
3. One atomic claim per assertion. Split compound sentences into multiple
   assertions that may share the same evidence sentence.
4. Use ONLY the supplied CONTENT. No outside knowledge, no inference beyond
   the text. If something is ambiguous, add a short uncertainty flag instead
   of guessing.
5. Cover the entire CONTENT: every factual statement, definition, numeric
   relationship, and caption fact should yield at least one assertion."""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_prompt(request: dict) -> tuple[str, str]:
    unit = request["source_unit"]
    role = request.get("task_role", "PRIMARY")
    instructions = request.get("task_instructions", "")
    if role == "COLD_AUDIT":
        target = request.get("audit_target") or {}
        system = (
            "You are an independent skeptical auditor inside a governed factory. "
            "You judge only from the supplied source bytes. When not affirmatively "
            "convinced, you mark the candidate unsupported."
        )
        user = (
            f"TASK: {instructions}\n\n"
            f"SOURCE UNIT ID: {unit['source_unit_id']}\n"
            f"SOURCE CONTENT:\n<<<CONTENT_START>>>\n{unit['content']}\n<<<CONTENT_END>>>\n\n"
            "CANDIDATE UNDER AUDIT:\n"
            f"  proposition: {target.get('proposition')}\n"
            f"  evidence:    {target.get('evidence')}\n"
            f"  polarity:    {target.get('polarity')}   certainty: {target.get('certainty')}\n\n"
            'Reply with ONLY: {"verdict": {"supported": true|false, "flags": [str], "rationale": str}}'
        )
        return system, user
    system = (
        "You are a precision extraction worker inside a governed factory. "
        "Your output is noncanonical candidate data that later review stages depend on. "
        "Faithfulness to the source bytes outranks fluency."
    )
    user = (
        f"ROLE: {role}\n"
        f"TASK: {instructions}\n\n"
        f"{PRESERVATION_RULES}\n\n"
        f"{RESPONSE_SCHEMA_HINT}\n\n"
        f"SOURCE UNIT ID: {unit['source_unit_id']}\n"
        f"REPRESENTATION: {unit.get('content_representation')}\n"
        f"CONTENT:\n<<<CONTENT_START>>>\n{unit['content']}\n<<<CONTENT_END>>>"
    )
    return system, user


def _extract_json_object(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    if start < 0:
        raise ValueError("no_json_object_in_model_output")
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError("unbalanced_json_object_in_model_output")


def call_claude(model: str, system: str, user: str, timeout: int) -> str:
    exe = shutil.which("claude")
    if not exe:
        raise RuntimeError("claude_cli_not_found_on_path")
    prompt = system + "\n\n" + user
    proc = subprocess.run(
        [exe, "--model", model, "-p", "--output-format", "json"],
        input=prompt, capture_output=True, text=True, encoding="utf-8",
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude_cli_failed:rc={proc.returncode}:stderr={proc.stderr[-2000:]}")
    envelope = json.loads(proc.stdout)
    if isinstance(envelope, dict) and "result" in envelope:
        if envelope.get("is_error"):
            raise RuntimeError(f"claude_cli_reported_error:{str(envelope)[:2000]}")
        return str(envelope["result"])
    return proc.stdout


def call_ollama(model: str, system: str, user: str, timeout: int, host: str) -> str:
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {"temperature": 0.2, "num_ctx": 16384, "num_predict": 8192},
    }).encode("utf-8")
    req = urllib.request.Request(
        host.rstrip("/") + "/api/chat", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    message = payload.get("message") or {}
    content = message.get("content") or ""
    if not content.strip() and message.get("thinking"):
        content = message["thinking"]
    return content


_SENT_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def call_echo(request: dict) -> dict:
    content = request["source_unit"]["content"]
    sentences = [s.strip() for s in _SENT_END.split(re.sub(r"\s+", " ", content).strip()) if len(s.strip()) >= 5]
    return {"assertions": [
        {"proposition": s, "evidence": s, "uncertainty_flags": ["ECHO_BACKEND_NOT_EMPIRICAL"]}
        for s in sentences
    ]}


def validate_assertions(raw_assertions: list, content: str) -> tuple[list, list]:
    valid, rejected = [], []
    for idx, item in enumerate(raw_assertions[:MAX_ASSERTIONS_PER_UNIT]):
        if not isinstance(item, dict):
            rejected.append({"ordinal": idx, "reason": "not_an_object"})
            continue
        proposition = str(item.get("proposition") or "").strip()
        evidence = str(item.get("evidence") or "")
        if not proposition or not evidence.strip():
            rejected.append({"ordinal": idx, "reason": "missing_proposition_or_evidence"})
            continue
        if evidence not in content:
            trimmed = evidence.strip()
            if trimmed in content:
                evidence = trimmed
            else:
                # Whitespace-exact recovery: locate the span the model plainly
                # meant, then use the source's own bytes for it. Uniqueness is
                # required; anything else is rejected, not repaired.
                pattern = re.escape(re.sub(r"\s+", " ", trimmed))
                pattern = pattern.replace(r"\ ", r"\s+")
                matches = list(re.finditer(pattern, content))
                if len(matches) == 1:
                    evidence = matches[0].group(0)
                else:
                    rejected.append({
                        "ordinal": idx,
                        "reason": "evidence_not_exact_source_substring",
                        "evidence_head": trimmed[:120],
                    })
                    continue
        cleaned = dict(item)
        cleaned["proposition"] = proposition
        cleaned["evidence"] = evidence
        nv = cleaned.get("numeric_values")
        cleaned["numeric_values"] = [x for x in nv if isinstance(x, dict)] if isinstance(nv, list) else []
        q = cleaned.get("qualifiers")
        cleaned["qualifiers"] = [str(x) for x in q] if isinstance(q, list) else []
        uf = cleaned.get("uncertainty_flags")
        cleaned["uncertainty_flags"] = [str(x) for x in uf] if isinstance(uf, list) else []
        if cleaned.get("polarity") not in ("AFFIRMATIVE", "NEGATIVE"):
            cleaned["polarity"] = "AFFIRMATIVE"
        if cleaned.get("certainty") not in ("ASSERTED", "HEDGED"):
            cleaned["certainty"] = "ASSERTED"
        valid.append(cleaned)
    return valid, rejected


def run(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="llm_provider")
    parser.add_argument("--backend", choices=["claude", "ollama", "echo"], required=True)
    parser.add_argument("--model", default="echo")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--ollama-host", default="http://127.0.0.1:11434")
    args = parser.parse_args(argv)

    stdin = sys.stdin
    if hasattr(stdin, "reconfigure"):
        stdin.reconfigure(encoding="utf-8")
    request = json.loads(stdin.read())
    unit = request["source_unit"]
    role = request.get("task_role", "PRIMARY")
    system, user = build_prompt(request)

    started = time.time()
    attempts = 0
    last_error = None
    raw_text = None
    parsed = None
    while attempts <= args.max_retries:
        attempts += 1
        try:
            if args.backend == "echo":
                if role == "COLD_AUDIT":
                    parsed = {"verdict": {"supported": True, "flags": ["ECHO_BACKEND_NOT_EMPIRICAL"], "rationale": "echo"}}
                else:
                    parsed = call_echo(request)
                raw_text = json.dumps(parsed)
            else:
                suffix = "" if attempts == 1 else (
                    "\n\nYour previous reply was not one valid JSON object. "
                    "Reply again with ONLY the JSON object, nothing else."
                )
                if args.backend == "claude":
                    raw_text = call_claude(args.model, system, user + suffix, args.timeout)
                else:
                    raw_text = call_ollama(args.model, system, user + suffix, args.timeout, args.ollama_host)
                parsed = _extract_json_object(raw_text)
            if role == "COLD_AUDIT":
                verdict = parsed.get("verdict")
                if not isinstance(verdict, dict) or not isinstance(verdict.get("supported"), bool):
                    raise ValueError("model_output_missing_boolean_verdict")
            elif not isinstance(parsed.get("assertions"), list):
                raise ValueError("model_output_missing_assertions_list")
            break
        except Exception as exc:  # noqa: BLE001 — every failure mode retries once, then hard-fails
            last_error = exc
            parsed = None
    if parsed is None:
        print(f"provider_failed_after_{attempts}_attempts:{type(last_error).__name__}:{last_error}", file=sys.stderr)
        return 3

    receipt = {
        "backend": args.backend,
        "model": args.model,
        "attempts": attempts,
        "duration_seconds": round(time.time() - started, 3),
        "request_sha256": _sha256(json.dumps(request, sort_keys=True, ensure_ascii=False)),
        "raw_output_sha256": _sha256(raw_text or ""),
        "empirical_semantic_model": args.backend != "echo",
    }
    if role == "COLD_AUDIT":
        raw_flags = parsed["verdict"].get("flags")
        response = {
            "provider_output_schema": "hermes-semantic-provider-1.1",
            "role": role,
            "verdict": {
                "supported": bool(parsed["verdict"]["supported"]),
                "flags": [str(x) for x in raw_flags][:20] if isinstance(raw_flags, list) else [],
                "rationale": str(parsed["verdict"].get("rationale") or "")[:2000],
            },
            "provider_receipt": receipt,
        }
    else:
        valid, rejected = validate_assertions(parsed["assertions"], unit["content"])
        receipt["emitted_count"] = len(valid)
        receipt["rejected_count"] = len(rejected)
        response = {
            "provider_output_schema": "hermes-semantic-provider-1.1",
            "role": role,
            "assertions": valid,
            "provider_receipt": receipt,
        }
        if rejected:
            response["provider_diagnostics"] = {"rejected": rejected}
    out = sys.stdout
    if hasattr(out, "reconfigure"):
        out.reconfigure(encoding="utf-8")
    json.dump(response, out, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(run())
