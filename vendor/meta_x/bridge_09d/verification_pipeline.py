"""Compatibility shim for the canonical verifier persistence pipeline.

Turn 5 has one verification persistence authority: bridge_09d.verifier_pipeline.
"""
from .verifier_pipeline import *  # noqa: F401,F403

# Early Turn-5 name retained for compatibility.
run_verification_pipeline = run_verifier_pipeline
