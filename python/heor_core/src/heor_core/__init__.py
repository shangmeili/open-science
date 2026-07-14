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
from .relative_effect import RelativeEffectError, derive_relative_effect_schedule

__all__ = [
    "AnalysisResult",
    "BackgroundMortalityError",
    "MarkovSpecification",
    "ModelValidationError",
    "RelativeEffectError",
    "derive_background_mortality_schedule",
    "derive_relative_effect_schedule",
    "run_markov",
]

__version__ = "0.1.0"
