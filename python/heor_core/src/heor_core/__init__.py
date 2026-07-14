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
from .hazard_ratio import HazardRatioError, derive_hazard_ratio_schedule
from .relative_effect import RelativeEffectError, derive_relative_effect_schedule
from .partitioned_survival import run_partitioned_survival
from .survival_materialization import validate_survival_curve_materializations

__all__ = [
    "AnalysisResult",
    "BackgroundMortalityError",
    "HazardRatioError",
    "MarkovSpecification",
    "ModelValidationError",
    "RelativeEffectError",
    "derive_background_mortality_schedule",
    "derive_hazard_ratio_schedule",
    "derive_relative_effect_schedule",
    "run_markov",
    "run_partitioned_survival",
    "validate_survival_curve_materializations",
]

__version__ = "0.1.0"
