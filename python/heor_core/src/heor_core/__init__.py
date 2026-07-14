"""Deterministic pharmacoeconomic analysis primitives."""

from .background_mortality import (
    BackgroundMortalityError,
    derive_background_mortality_schedule,
)
from .model import (
    AnalysisResult,
    MarkovSpecification,
    ModelValidationError,
    run_markov,
)

__all__ = [
    "AnalysisResult",
    "BackgroundMortalityError",
    "MarkovSpecification",
    "ModelValidationError",
    "derive_background_mortality_schedule",
    "run_markov",
]

__version__ = "0.1.0"
