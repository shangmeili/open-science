"""Independent, dependency-free survival and hazard evaluator for survHE outputs."""

from __future__ import annotations

from math import erfc, exp, expm1, isfinite, lgamma, log, log1p, pi, sqrt
from typing import Mapping

MAX_ITERATIONS = 10_000
EPSILON = 2.0e-14
FPMIN = 1.0e-300

PARAMETERIZATIONS = {
    "exponential": "exponential_rate",
    "weibull": "weibull_shape_scale_aft",
    "gompertz": "gompertz_shape_rate",
    "gamma": "gamma_shape_rate",
    "generalized_gamma": "generalized_gamma_prentice",
    "generalized_f": "generalized_f_prentice",
    "lognormal": "lognormal_meanlog_sdlog",
    "loglogistic": "loglogistic_shape_scale",
}


def curve(family: str, p: Mapping[str, float], time: float) -> tuple[float, float | None]:
    if not isfinite(time) or time < 0:
        raise ValueError("time must be finite and non-negative")
    _validate(family, p)
    if time == 0:
        return 1.0, None
    if family == "exponential":
        survival, hazard = exp(-p["rate"] * time), p["rate"]
    elif family == "weibull":
        power = (time / p["scale"]) ** p["shape"]
        survival = exp(-power)
        hazard = p["shape"] * power / time
    elif family == "gompertz":
        scaled = p["shape"] * time
        exprel = expm1(scaled) / scaled if scaled else 1.0
        survival = exp(-p["rate"] * time * exprel)
        hazard = p["rate"] * exp(scaled)
    elif family == "gamma":
        x = p["rate"] * time
        survival = gamma_q(p["shape"], x)
        log_density = p["shape"] * log(p["rate"]) + (p["shape"] - 1) * log(time) - x - lgamma(p["shape"])
        hazard = _hazard(exp(log_density), survival)
    elif family == "lognormal":
        z = (log(time) - p["meanlog"]) / p["sdlog"]
        survival = 0.5 * erfc(z / sqrt(2.0))
        density = exp(-0.5 * z * z) / (time * p["sdlog"] * sqrt(2.0 * pi))
        hazard = _hazard(density, survival)
    elif family == "loglogistic":
        log_odds = p["shape"] * (log(time) - log(p["scale"]))
        survival = inverse_one_plus_exp(log_odds)
        hazard = p["shape"] * (1.0 - survival) / time
    elif family == "generalized_gamma":
        survival, density = _generalized_gamma(p, time)
        hazard = _hazard(density, survival)
    elif family == "generalized_f":
        survival, density = _generalized_f(p, time)
        hazard = _hazard(density, survival)
    else:
        raise ValueError(f"unsupported survival family {family}")
    if not isfinite(survival) or not 0 <= survival <= 1 or not isfinite(hazard) or hazard < 0:
        raise ValueError(f"{family} evaluation is outside its admitted range")
    return min(1.0, max(0.0, survival)), hazard


def _validate(family: str, p: Mapping[str, float]) -> None:
    required = {
        "exponential": ("rate",), "weibull": ("shape", "scale"),
        "gompertz": ("shape", "rate"), "gamma": ("shape", "rate"),
        "generalized_gamma": ("mu", "sigma", "Q"),
        "generalized_f": ("mu", "sigma", "Q", "P"),
        "lognormal": ("meanlog", "sdlog"), "loglogistic": ("shape", "scale"),
    }.get(family)
    if required is None or set(p) != set(required) or any(not isfinite(p[name]) for name in required):
        raise ValueError(f"{family} parameters do not match the natural parameterization")
    positive = {
        "exponential": ("rate",), "weibull": ("shape", "scale"),
        "gompertz": ("rate",), "gamma": ("shape", "rate"),
        "generalized_gamma": ("sigma",), "generalized_f": ("sigma",),
        "lognormal": ("sdlog",), "loglogistic": ("shape", "scale"),
    }[family]
    if any(p[name] <= 0 for name in positive) or (family == "generalized_f" and p["P"] < 0):
        raise ValueError(f"{family} positive parameter constraint is violated")


def _generalized_gamma(p: Mapping[str, float], time: float) -> tuple[float, float]:
    q, sigma = p["Q"], p["sigma"]
    z0 = (log(time) - p["mu"]) / sigma
    if q == 0:
        survival = 0.5 * erfc(z0 / sqrt(2.0))
        return survival, exp(-0.5 * z0 * z0) / (time * sigma * sqrt(2.0 * pi))
    shape = 1.0 / (q * q)
    log_argument = q * z0 + log(shape)
    argument = exp(log_argument) if log_argument < 709 else float("inf")
    survival = gamma_q(shape, argument) if q > 0 else gamma_p(shape, argument)
    log_density = log(abs(q)) + shape * log_argument - argument - log(sigma) - log(time) - lgamma(shape)
    return survival, exp(log_density) if log_density > -746 else 0.0


def _generalized_f(p: Mapping[str, float], time: float) -> tuple[float, float]:
    if p["P"] == 0:
        return _generalized_gamma(p, time)
    total = p["Q"] ** 2 + 2 * p["P"]
    delta = sqrt(total)
    plus = total + p["Q"] * delta
    minus = total - p["Q"] * delta
    s1 = minus / (p["P"] * total) if abs(plus) < abs(minus) else 2 / plus
    s2 = plus / (p["P"] * total) if abs(minus) < abs(plus) else 2 / minus
    log_ratio = log(s1 / s2) + delta * (log(time) - p["mu"]) / p["sigma"]
    x = inverse_one_plus_exp(log_ratio)
    survival = (
        1 - regularized_beta(inverse_one_plus_exp(-log_ratio), s1, s2)
        if log_ratio < 0
        else regularized_beta(x, s2, s1)
    )
    log_x = -_softplus(log_ratio)
    log_y = -_softplus(-log_ratio)
    log_density = log(delta) - log(p["sigma"]) - log(time) - (lgamma(s1) + lgamma(s2) - lgamma(s1 + s2)) + s1 * log_y + s2 * log_x
    return survival, exp(log_density) if log_density > -746 else 0.0


def gamma_p(a: float, x: float) -> float:
    if x == 0: return 0.0
    if x == float("inf"): return 1.0
    if x >= a + 1: return 1 - gamma_q(a, x)
    term = total = 1 / a
    denominator = a
    for _ in range(MAX_ITERATIONS):
        denominator += 1; term *= x / denominator; total += term
        if abs(term) <= abs(total) * EPSILON:
            return _unit(total * exp(-x + a * log(x) - lgamma(a)))
    raise ValueError("regularized gamma series did not converge")


def gamma_q(a: float, x: float) -> float:
    if x == 0: return 1.0
    if x == float("inf"): return 0.0
    if x < a + 1: return 1 - gamma_p(a, x)
    b = x + 1 - a; c = 1 / FPMIN; d = 1 / max(abs(b), FPMIN)
    if b < 0: d = -d
    result = d
    for index in range(1, MAX_ITERATIONS + 1):
        coefficient = -index * (index - a); b += 2
        d = coefficient * d + b; d = FPMIN if abs(d) < FPMIN else d
        c = b + coefficient / c; c = FPMIN if abs(c) < FPMIN else c
        d = 1 / d; delta = d * c; result *= delta
        if abs(delta - 1) <= EPSILON:
            return _unit(exp(-x + a * log(x) - lgamma(a)) * result)
    raise ValueError("regularized gamma fraction did not converge")


def regularized_beta(x: float, a: float, b: float) -> float:
    if x == 0: return 0.0
    if x == 1: return 1.0
    front = exp(lgamma(a + b) - lgamma(a) - lgamma(b) + a * log(x) + b * log1p(-x))
    if x < (a + 1) / (a + b + 2): return _unit(front * _beta_fraction(a, b, x) / a)
    return _unit(1 - front * _beta_fraction(b, a, 1 - x) / b)


def _beta_fraction(a: float, b: float, x: float) -> float:
    qab, qap, qam = a + b, a + 1, a - 1
    c = 1.0; d = 1 - qab * x / qap; d = FPMIN if abs(d) < FPMIN else d
    d = 1 / d; result = d
    for index in range(1, MAX_ITERATIONS + 1):
        doubled = 2 * index
        coefficient = index * (b - index) * x / ((qam + doubled) * (a + doubled))
        d = 1 + coefficient * d; d = FPMIN if abs(d) < FPMIN else d
        c = 1 + coefficient / c; c = FPMIN if abs(c) < FPMIN else c
        d = 1 / d; result *= d * c
        coefficient = -(a + index) * (qab + index) * x / ((a + doubled) * (qap + doubled))
        d = 1 + coefficient * d; d = FPMIN if abs(d) < FPMIN else d
        c = 1 + coefficient / c; c = FPMIN if abs(c) < FPMIN else c
        d = 1 / d; delta = d * c; result *= delta
        if abs(delta - 1) <= EPSILON: return result
    raise ValueError("regularized beta fraction did not converge")


def inverse_one_plus_exp(value: float) -> float:
    if value >= 0:
        scaled = exp(-value) if value < 746 else 0.0
        return scaled / (1 + scaled)
    scaled = exp(value) if value > -746 else 0.0
    return 1 / (1 + scaled)


def _softplus(value: float) -> float:
    if value > 0:
        return value + log1p(exp(-value))
    return log1p(exp(value))


def _hazard(density: float, survival: float) -> float:
    if survival <= 0: raise ValueError("hazard is not finite after survival underflow")
    return density / survival


def _unit(value: float) -> float:
    if not isfinite(value) or value < -1e-12 or value > 1 + 1e-12: raise ValueError("special function result outside [0,1]")
    return min(1.0, max(0.0, value))
