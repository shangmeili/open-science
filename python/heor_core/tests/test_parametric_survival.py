from __future__ import annotations

import unittest

from heor_core.model import ModelValidationError
from heor_core.parametric_survival import survival


class ParametricSurvivalTests(unittest.TestCase):
    """Golden values produced by flexsurv 2.3.2 on its natural parameter scale."""

    def test_all_admitted_families_match_flexsurv_golden_values(self) -> None:
        cases = {
            "exponential": ({"rate_per_year": 0.2}, 0.54881163609402639),
            "weibull": ({"shape": 1.5, "scale_years": 4.0}, 0.52229691358254149),
            "gompertz": ({"shape_per_year": -0.05, "rate_per_year": 0.2}, 0.57282896667618433),
            "gamma": ({"shape": 2.5, "rate_per_year": 0.7}, 0.52099495343140501),
            "lognormal": ({"meanlog_years": 1.2, "sdlog": 0.8}, 0.55042478560434971),
            "loglogistic": ({"shape": 1.7, "scale_years": 3.2}, 0.52740139000484665),
            "generalized_gamma": ({"mu_log_years": 1.0, "sigma": 0.7, "Q": -0.6}, 0.52544565028022161),
            "generalized_f": ({"mu_log_years": 1.0, "sigma": 0.8, "Q": -0.3, "P": 0.9}, 0.49721403432450395),
        }
        for family, (parameters, expected) in cases.items():
            with self.subTest(family=family):
                self.assertAlmostEqual(survival(family, parameters, 3.0), expected, places=12)

    def test_limit_parameterizations_match_their_nested_families(self) -> None:
        lognormal = {"meanlog_years": 1.0, "sdlog": 0.7}
        generalized_gamma = {"mu_log_years": 1.0, "sigma": 0.7, "Q": 0.0}
        generalized_f = {**generalized_gamma, "P": 0.0}
        expected = survival("lognormal", lognormal, 3.0)
        self.assertAlmostEqual(survival("generalized_gamma", generalized_gamma, 3.0), expected, places=14)
        self.assertAlmostEqual(survival("generalized_f", generalized_f, 3.0), expected, places=14)

    def test_invalid_evaluation_time_fails_closed(self) -> None:
        with self.assertRaisesRegex(ModelValidationError, "non-negative"):
            survival("exponential", {"rate_per_year": 0.2}, -1.0)


if __name__ == "__main__":
    unittest.main()
