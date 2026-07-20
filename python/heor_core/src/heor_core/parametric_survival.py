"""Dependency-free survival functions for admitted natural parameterizations."""

from __future__ import annotations

from math import erfc, exp, expm1, isfinite, lgamma, log, log1p, sqrt
from typing import Mapping

from .model import ModelValidationError


MAX_ITERATIONS = 10_000
EPSILON = 2.0e-14
FPMIN = 1.0e-300
SQRT_TWO = sqrt(2.0)


PARAMETERIZATIONS: dict[str, tuple[str, tuple[str, ...]]] = {
    "exponential": ("exponential_rate", ("rate_per_year",)),
    "weibull": ("weibull_shape_scale_aft", ("shape", "scale_years")),
    "gompertz": ("gompertz_shape_rate", ("shape_per_year", "rate_per_year")),
    "gamma": ("gamma_shape_rate", ("shape", "rate_per_year")),
    "generalized_gamma": (
        "generalized_gamma_prentice",
        ("mu_log_years", "sigma", "Q"),
    ),
    "generalized_f": (
        "generalized_f_prentice",
        ("mu_log_years", "sigma", "Q", "P"),
    ),
    "lognormal": ("lognormal_meanlog_sdlog", ("meanlog_years", "sdlog")),
    "loglogistic": ("loglogistic_shape_scale", ("shape", "scale_years")),
}


def survival(family: str, parameters: Mapping[str, float], time_years: float) -> float:
    """Evaluate one admitted survival function on a year-based time scale."""

    if not isfinite(time_years) or time_years < 0.0:
        raise ModelValidationError("survival evaluation time must be finite and non-negative")
    if time_years == 0.0:
        return 1.0
    try:
        if family == "exponential":
            value = exp(-parameters["rate_per_year"] * time_years)
        elif family == "weibull":
            value = exp(-((time_years / parameters["scale_years"]) ** parameters["shape"]))
        elif family == "gompertz":
            shape = parameters["shape_per_year"]
            scaled = shape * time_years
            exprel = expm1(scaled) / scaled if scaled != 0.0 else 1.0
            value = exp(-parameters["rate_per_year"] * time_years * exprel)
        elif family == "gamma":
            value = regularized_gamma_q(
                parameters["shape"], parameters["rate_per_year"] * time_years
            )
        elif family == "lognormal":
            z = (log(time_years) - parameters["meanlog_years"]) / parameters["sdlog"]
            value = 0.5 * erfc(z / SQRT_TWO)
        elif family == "loglogistic":
            log_odds = parameters["shape"] * (
                log(time_years) - log(parameters["scale_years"])
            )
            value = _inverse_one_plus_exp(log_odds)
        elif family == "generalized_gamma":
            value = _generalized_gamma_survival(parameters, time_years)
        elif family == "generalized_f":
            value = _generalized_f_survival(parameters, time_years)
        else:
            raise ModelValidationError(f"unsupported survival family {family}")
    except (ArithmeticError, KeyError, OverflowError, ValueError) as error:
        raise ModelValidationError(f"{family} survival evaluation failed") from error
    if not isfinite(value) or value < 0.0 or value > 1.0:
        raise ModelValidationError(f"{family} survival evaluation is outside [0,1]")
    return min(1.0, max(0.0, value))


def regularized_gamma_p(shape: float, x: float) -> float:
    if not isfinite(shape) or shape <= 0.0 or x < 0.0 or not isfinite(x):
        if x == float("inf") and isfinite(shape) and shape > 0.0:
            return 1.0
        raise ModelValidationError("regularized gamma arguments are invalid")
    if x == 0.0:
        return 0.0
    if x >= shape + 1.0:
        return 1.0 - regularized_gamma_q(shape, x)
    term = 1.0 / shape
    total = term
    denominator = shape
    for _ in range(1, MAX_ITERATIONS + 1):
        denominator += 1.0
        term *= x / denominator
        total += term
        if abs(term) <= abs(total) * EPSILON:
            return _unit(total * exp(-x + shape * log(x) - lgamma(shape)))
    raise ModelValidationError("regularized gamma series did not converge")


def regularized_gamma_q(shape: float, x: float) -> float:
    if not isfinite(shape) or shape <= 0.0 or x < 0.0:
        raise ModelValidationError("regularized gamma arguments are invalid")
    if x == float("inf"):
        return 0.0
    if not isfinite(x):
        raise ModelValidationError("regularized gamma arguments are invalid")
    if x == 0.0:
        return 1.0
    if x < shape + 1.0:
        return 1.0 - regularized_gamma_p(shape, x)
    b = x + 1.0 - shape
    c = 1.0 / FPMIN
    d = 1.0 / max(abs(b), FPMIN)
    if b < 0.0:
        d = -d
    result = d
    for index in range(1, MAX_ITERATIONS + 1):
        coefficient = -float(index) * (float(index) - shape)
        b += 2.0
        d = coefficient * d + b
        if abs(d) < FPMIN:
            d = FPMIN
        c = b + coefficient / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        delta = d * c
        result *= delta
        if abs(delta - 1.0) <= EPSILON:
            return _unit(exp(-x + shape * log(x) - lgamma(shape)) * result)
    raise ModelValidationError("regularized gamma continued fraction did not converge")


def regularized_beta(x: float, a: float, b: float) -> float:
    if not all(isfinite(value) for value in (x, a, b)) or not 0.0 <= x <= 1.0 or a <= 0.0 or b <= 0.0:
        raise ModelValidationError("regularized beta arguments are invalid")
    if x == 0.0:
        return 0.0
    if x == 1.0:
        return 1.0
    front = exp(lgamma(a + b) - lgamma(a) - lgamma(b) + a * log(x) + b * log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return _unit(front * _beta_fraction(a, b, x) / a)
    return _unit(1.0 - front * _beta_fraction(b, a, 1.0 - x) / b)


def _beta_fraction(a: float, b: float, x: float) -> float:
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    result = d
    for index in range(1, MAX_ITERATIONS + 1):
        doubled = 2.0 * index
        coefficient = index * (b - index) * x / ((qam + doubled) * (a + doubled))
        d = 1.0 + coefficient * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + coefficient / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        result *= d * c
        coefficient = -(a + index) * (qab + index) * x / ((a + doubled) * (qap + doubled))
        d = 1.0 + coefficient * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + coefficient / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        delta = d * c
        result *= delta
        if abs(delta - 1.0) <= EPSILON:
            return result
    raise ModelValidationError("regularized beta continued fraction did not converge")


def _generalized_gamma_survival(parameters: Mapping[str, float], time_years: float) -> float:
    mu = parameters["mu_log_years"]
    sigma = parameters["sigma"]
    q = parameters["Q"]
    if q == 0.0:
        z = (log(time_years) - mu) / sigma
        return 0.5 * erfc(z / SQRT_TWO)
    shape = 1.0 / (q * q)
    log_argument = q * (log(time_years) - mu) / sigma + log(shape)
    argument = exp(log_argument) if log_argument < 709.0 else float("inf")
    return regularized_gamma_q(shape, argument) if q > 0.0 else regularized_gamma_p(shape, argument)


def _generalized_f_survival(parameters: Mapping[str, float], time_years: float) -> float:
    p = parameters["P"]
    if p == 0.0:
        return _generalized_gamma_survival(parameters, time_years)
    q = parameters["Q"]
    total = q * q + 2.0 * p
    delta = sqrt(total)
    plus = total + q * delta
    minus = total - q * delta
    s1 = minus / (p * total) if abs(plus) < abs(minus) else 2.0 / plus
    s2 = plus / (p * total) if abs(minus) < abs(plus) else 2.0 / minus
    log_ratio = log(s1 / s2) + delta * (
        log(time_years) - parameters["mu_log_years"]
    ) / parameters["sigma"]
    beta_x = _inverse_one_plus_exp(log_ratio)
    if log_ratio < 0.0:
        beta_y = _inverse_one_plus_exp(-log_ratio)
        return 1.0 - regularized_beta(beta_y, s1, s2)
    return regularized_beta(beta_x, s2, s1)


def _inverse_one_plus_exp(value: float) -> float:
    if value >= 0.0:
        scaled = exp(-value) if value < 746.0 else 0.0
        return scaled / (1.0 + scaled)
    scaled = exp(value) if value > -746.0 else 0.0
    return 1.0 / (1.0 + scaled)


def _unit(value: float) -> float:
    if not isfinite(value) or value < -1.0e-12 or value > 1.0 + 1.0e-12:
        raise ModelValidationError("special-function result is outside [0,1]")
    return min(1.0, max(0.0, value))
