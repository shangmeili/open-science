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
from .economic_inputs import EconomicSpecification
from .cost_input_normalization import (
    CostNormalizationSummary,
    validate_cost_input_normalization,
)
from .utility_inputs import UtilityInputSummary, validate_utility_inputs
from .event_disutilities import EventDisutilitySummary, validate_event_disutilities
from .hazard_ratio import HazardRatioError, derive_hazard_ratio_schedule
from .relative_effect import RelativeEffectError, derive_relative_effect_schedule
from .partitioned_survival import run_partitioned_survival
from .joint_survival_uncertainty import validate_joint_survival_uncertainty
from .survival_materialization import validate_survival_curve_materializations
from .treatment_effect_duration import validate_treatment_effect_duration
from .decision_tree import DecisionTreeSpecification, run_decision_tree

__all__ = [
    "AnalysisResult",
    "BackgroundMortalityError",
    "HazardRatioError",
    "EconomicSpecification",
    "CostNormalizationSummary",
    "MarkovSpecification",
    "ModelValidationError",
    "RelativeEffectError",
    "derive_background_mortality_schedule",
    "derive_hazard_ratio_schedule",
    "derive_relative_effect_schedule",
    "run_markov",
    "run_partitioned_survival",
    "validate_joint_survival_uncertainty",
    "validate_cost_input_normalization",
    "UtilityInputSummary",
    "validate_utility_inputs",
    "EventDisutilitySummary",
    "validate_event_disutilities",
    "validate_survival_curve_materializations",
    "validate_treatment_effect_duration",
    "DecisionTreeSpecification",
    "run_decision_tree",
]

__version__ = "0.1.0"
