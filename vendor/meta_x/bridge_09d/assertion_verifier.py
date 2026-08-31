"""Compatibility import surface for the canonical Turn-5 verifier.

There is exactly one semantic verification authority: :mod:`bridge_09d.verifier`.
This module remains only so early Turn-5 callers do not fork onto a second engine.
"""
from .verifier import *  # noqa: F401,F403
