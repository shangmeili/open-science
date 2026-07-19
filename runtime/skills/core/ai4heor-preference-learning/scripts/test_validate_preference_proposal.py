#!/usr/bin/env python3

from __future__ import annotations

import unittest

from validate_preference_proposal import validate


def fixture() -> dict:
    return {
        "schema": "ai4heor-preference-proposal/v1",
        "id": "concise-result-first",
        "status": "proposal",
        "created_at": "2026-07-19T00:00:00Z",
        "scope": "presentation",
        "proposed_rule": "Lead with the result and keep the handoff concise.",
        "evidence": [
            {"interaction_ref": "session-a", "observed_at": "2026-07-17T00:00:00Z", "summary": "Requested result-first copy."},
            {"interaction_ref": "session-b", "observed_at": "2026-07-19T00:00:00Z", "summary": "Repeated the same presentation request."},
        ],
        "counterexamples": [],
        "review_condition": "Review when the output format changes.",
        "expires_at": None,
        "contains_sensitive_data": False,
        "changes_scientific_authority": False,
    }


class PreferenceProposalTests(unittest.TestCase):
    def test_two_independent_observations_pass(self) -> None:
        self.assertEqual(validate(fixture()), [])

    def test_one_observation_and_authority_change_fail(self) -> None:
        value = fixture()
        value["evidence"] = value["evidence"][:1]
        value["changes_scientific_authority"] = True
        errors = validate(value)
        self.assertIn("evidence must contain at least two independent interactions", errors)
        self.assertIn("changes_scientific_authority must be false", errors)


if __name__ == "__main__":
    unittest.main()
