"""Bracket one Ollama semantic-provider request with immutable tag-digest checks.

This wrapper is invoked by run_appliance for Ollama roles. It verifies that the
configured model tag resolves to the expected immutable digest immediately before
and after the delegated llm_provider.py process. Provider stdout is released to
Hermes only when the digest is stable across the semantic request; otherwise the
result is discarded and the work item fails/retries under normal factory policy.

This materially narrows mutable-tag TOCTOU risk. It does not claim that Ollama
itself accepts a digest-pinned model identifier or that an adversary could not
retag-and-restore entirely inside the guarded interval.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
LLM_PROVIDER = HERE / "llm_provider.py"
DIGEST_RE = re.compile(r"^(?:sha256:)?([0-9a-f]{64})$", re.IGNORECASE)


def normalize_host(host: str) -> str:
    value = str(host or "").strip().rstrip("/")
    if not value:
        value = "http://127.0.0.1:11434"
    if "://" not in value:
        value = "http://" + value
    return value


def normalize_digest(value: str) -> str:
    match = DIGEST_RE.fullmatch(str(value or "").strip())
    if not match:
        raise ValueError(f"ollama_digest_invalid:{value}")
    return "sha256:" + match.group(1).lower()


def resolve_digest(model: str, host: str, *, timeout: int = 15) -> str:
    host = normalize_host(host)
    request = urllib.request.Request(host + "/api/tags", method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    rows = payload.get("models")
    if not isinstance(rows, list):
        raise RuntimeError("ollama_tags_response_missing_models")
    matches = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        names = {str(row.get("name") or ""), str(row.get("model") or "")}
        if model in names:
            matches.append(row)
    if len(matches) != 1:
        raise RuntimeError(f"ollama_model_digest_resolution_failed:{model}:matches={len(matches)}")
    return normalize_digest(str(matches[0].get("digest") or ""))


def assert_expected_digest(model: str, host: str, expected_digest: str, *, phase: str, timeout: int = 15) -> str:
    expected = normalize_digest(expected_digest)
    measured = resolve_digest(model, host, timeout=timeout)
    if measured != expected:
        raise RuntimeError(f"ollama_digest_{phase}_mismatch:{model}:{measured}!={expected}")
    return measured


def delegated_command(args: argparse.Namespace) -> list[str]:
    command = [
        sys.executable, "-B", str(LLM_PROVIDER),
        "--backend", "ollama",
        "--model", args.model,
        "--timeout", str(args.timeout),
        "--max-retries", str(args.max_retries),
        "--ollama-host", normalize_host(args.ollama_host),
        "--ollama-keep-alive", args.ollama_keep_alive,
        "--temperature", str(args.temperature),
    ]
    if args.ollama_think is not None:
        command += ["--ollama-think", args.ollama_think]
    return command


def delegate_timeout_seconds(args: argparse.Namespace) -> int:
    """Cover every configured provider attempt plus process/guard overhead."""
    attempts = max(1, int(args.max_retries) + 1)
    return max(30, attempts * max(1, int(args.timeout)) + 60)


def execute_guarded(args: argparse.Namespace, request_text: str) -> tuple[int, str, str]:
    host = normalize_host(args.ollama_host)
    expected = normalize_digest(args.expected_digest)
    before = assert_expected_digest(args.model, host, expected, phase="before", timeout=args.digest_timeout)

    proc = subprocess.run(
        delegated_command(args),
        input=request_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=delegate_timeout_seconds(args),
    )

    # Always perform the post-call check when the delegate returned. A digest
    # drift invalidates even otherwise successful output.
    after = assert_expected_digest(args.model, host, expected, phase="after", timeout=args.digest_timeout)
    if proc.returncode != 0:
        return proc.returncode, proc.stdout, proc.stderr

    try:
        output = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"guarded_provider_stdout_not_json:{exc}") from exc
    if not isinstance(output, dict):
        raise RuntimeError("guarded_provider_stdout_not_object")
    receipt = output.get("provider_receipt")
    if not isinstance(receipt, dict):
        receipt = {}
        output["provider_receipt"] = receipt
    receipt["ollama_digest_guard"] = {
        "expected_digest": expected,
        "before_digest": before,
        "after_digest": after,
        "stable": before == expected == after,
        "model": args.model,
        "host": host,
    }
    return 0, json.dumps(output, ensure_ascii=False), proc.stderr


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ollama_digest_guard")
    parser.add_argument("--model", required=True)
    parser.add_argument("--expected-digest", required=True)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--digest-timeout", type=int, default=15)
    parser.add_argument("--ollama-host", default="http://127.0.0.1:11434")
    parser.add_argument("--ollama-think", choices=["false", "low", "medium", "high"])
    parser.add_argument("--ollama-keep-alive", default="30m")
    parser.add_argument("--temperature", type=float, default=0.0)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    stdin = sys.stdin
    if hasattr(stdin, "reconfigure"):
        stdin.reconfigure(encoding="utf-8")
    request_text = stdin.read()
    try:
        rc, stdout, stderr = execute_guarded(args, request_text)
    except Exception as exc:
        print(f"ollama_digest_guard_failed:{type(exc).__name__}:{exc}", file=sys.stderr)
        return 4
    if stderr:
        print(stderr, file=sys.stderr, end="" if stderr.endswith("\n") else "\n")
    if stdout:
        print(stdout)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
