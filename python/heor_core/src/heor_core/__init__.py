"""Deterministic pharmacoeconomic analysis primitives."""

from .model import (
    AnalysisResult,
    MarkovSpecification,
    ModelValidationError,
    run_markov,
)

__all__ = [
    "AnalysisResult",
    "MarkovSpecification",
    "ModelValidationError",
    "run_markov",
]

__version__ = "0.1.0"
