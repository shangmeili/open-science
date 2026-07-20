from __future__ import annotations

import copy
from contextlib import redirect_stdout
import hashlib
import importlib.util
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from heor_core.event_disutilities import validate_event_disutilities
from heor_core.cli import main as cli_main
from heor_core.model import ModelValidationError
from test_treatment_effect_duration import event_disutility_inputs


ROOT = Path(__file__).resolve().parents[3]
PORTABLE_PATH = ROOT / "runtime/skills/core/heor-event-disutilities/scripts/validate_event_disutilities.py"
PORTABLE_SPEC = importlib.util.spec_from_file_location(
    "portable_event_disutilities", PORTABLE_PATH
)
assert PORTABLE_SPEC is not None and PORTABLE_SPEC.loader is not None
PORTABLE = importlib.util.module_from_spec(PORTABLE_SPEC)
PORTABLE_SPEC.loader.exec_module(PORTABLE)
PSM_PORTABLE_PATH = ROOT / (
    "runtime/skills/core/heor-partitioned-survival/scripts/"
    "validate_partitioned_survival.py"
)
PSM_PORTABLE_SPEC = importlib.util.spec_from_file_location(
    "portable_partitioned_survival_event", PSM_PORTABLE_PATH
)
assert PSM_PORTABLE_SPEC is not None and PSM_PORTABLE_SPEC.loader is not None
PSM_PORTABLE = importlib.util.module_from_spec(PSM_PORTABLE_SPEC)
PSM_PORTABLE_SPEC.loader.exec_module(PSM_PORTABLE)


class EventDisutilityTests(unittest.TestCase):
    def test_cli_requires_and_consumes_event_artifact(self) -> None:
        inputs = event_disutility_inputs()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            names = [
                "analysis-plan.json",
                "partitioned-survival-plan.json",
                "survival-curve-materializations.json",
                "treatment-effect-duration.json",
                "cost-input-normalization.json",
                "utility-inputs.json",
                "event-disutilities.json",
            ]
            raws = [inputs[index] for index in (1, 3, 5, 7, 9, 11, 13)]
            paths = [root / name for name in names]
            for path, raw in zip(paths, raws):
                path.write_bytes(raw)
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(
                    cli_main(
                        [
                            str(paths[0]),
                            "--partitioned-survival-plan", str(paths[1]),
                            "--survival-curve-materializations", str(paths[2]),
                            "--treatment-effect-duration", str(paths[3]),
                            "--cost-input-normalization", str(paths[4]),
                            "--utility-inputs", str(paths[5]),
                            "--event-disutilities", str(paths[6]),
                        ]
                    ),
                    0,
                )
            self.assertEqual(json.loads(output.getvalue())["schema_version"], "0.7.0")

    def test_portable_validator_matches_core_contract(self) -> None:
        inputs = event_disutility_inputs()
        self.assertEqual(
            PORTABLE.validate(
                inputs[0], inputs[1], inputs[10], inputs[11], inputs[12]
            ),
            [],
        )

    def test_portable_psm_requires_and_binds_event_bytes(self) -> None:
        inputs = event_disutility_inputs()
        self.assertEqual(
            PSM_PORTABLE.validate(
                inputs[0],
                inputs[1],
                inputs[2],
                None,
                inputs[7],
                inputs[9],
                inputs[11],
                inputs[13],
            ),
            [],
        )
        self.assertTrue(
            PSM_PORTABLE.validate(
                inputs[0],
                inputs[1],
                inputs[2],
                None,
                inputs[7],
                inputs[9],
                inputs[11],
                b"stale",
            )
        )

    def test_portable_validator_rejects_overlap_and_arithmetic_drift(self) -> None:
        for mutation in ("overlap", "arithmetic"):
            with self.subTest(mutation=mutation):
                inputs = event_disutility_inputs()
                utility = copy.deepcopy(inputs[10])
                artifact = copy.deepcopy(inputs[12])
                if mutation == "overlap":
                    utility["items"]["intervention-progression-free"]["application"][
                        "excluded_effects"
                    ].remove("infusion-reaction")
                    utility_raw = json.dumps(
                        utility, sort_keys=True, separators=(",", ":")
                    ).encode()
                    artifact["base_utility_inputs"]["content_sha256"] = hashlib.sha256(
                        utility_raw
                    ).hexdigest()
                else:
                    utility_raw = inputs[11]
                    artifact["cycle_state_qaly_losses"]["intervention"][0][0] += 0.01
                self.assertTrue(
                    PORTABLE.validate(
                        inputs[0], inputs[1], utility, utility_raw, artifact
                    )
                )

    def test_reproduces_all_three_supported_modes(self) -> None:
        inputs = event_disutility_inputs()
        summary = validate_event_disutilities(
            inputs[0], inputs[1], inputs[10], inputs[11], inputs[12], inputs[13]
        )
        self.assertEqual(summary.item_count, 3)
        self.assertEqual(summary.one_time_item_count, 1)
        self.assertEqual(summary.recurrent_item_count, 1)
        self.assertEqual(summary.continuous_exposure_item_count, 1)
        self.assertGreater(
            summary.cycle_state_qaly_losses["intervention"][0][0], 0.02
        )

    def test_rejects_arithmetic_and_authority_drift(self) -> None:
        for mutation in ("arithmetic", "authority"):
            with self.subTest(mutation=mutation):
                inputs = event_disutility_inputs()
                artifact = copy.deepcopy(inputs[12])
                if mutation == "arithmetic":
                    artifact["items"]["intervention-infusion-reaction"][
                        "cycle_qaly_loss_per_eligible_person"
                    ][0] += 0.01
                else:
                    artifact["items"]["intervention-infusion-reaction"]["approved"] = True
                with self.assertRaises(ModelValidationError):
                    validate_event_disutilities(
                        inputs[0],
                        inputs[1],
                        inputs[10],
                        inputs[11],
                        artifact,
                        json.dumps(artifact).encode(),
                    )

    def test_requires_explicit_cross_artifact_event_exclusion(self) -> None:
        inputs = event_disutility_inputs()
        utility = copy.deepcopy(inputs[10])
        utility["items"]["intervention-progression-free"]["application"][
            "excluded_effects"
        ].remove("infusion-reaction")
        with self.assertRaisesRegex(ModelValidationError, "explicitly exclude"):
            validate_event_disutilities(
                inputs[0], inputs[1], utility, inputs[11], inputs[12], inputs[13]
            )

    def test_rejects_multi_cycle_one_time_probability(self) -> None:
        inputs = event_disutility_inputs()
        artifact = copy.deepcopy(inputs[12])
        item = artifact["items"]["intervention-infusion-reaction"]
        item["occurrence"]["schedule"] = [0.2, 0.1]
        item["cycle_qaly_loss_per_eligible_person"][1] = (
            0.1 * item["health_impact"]["qaly_loss_per_occurrence"]
        )
        with self.assertRaisesRegex(ModelValidationError, "exactly one cycle"):
            validate_event_disutilities(
                inputs[0], inputs[1], inputs[10], inputs[11], artifact, b"changed"
            )

    def test_rejects_duration_beyond_one_cycle(self) -> None:
        inputs = event_disutility_inputs()
        artifact = copy.deepcopy(inputs[12])
        item = artifact["items"]["intervention-infusion-reaction"]
        item["health_impact"]["duration_days"] = 400.0
        item["health_impact"]["qaly_loss_per_occurrence"] = 0.2 * 400.0 / 365.25
        item["cycle_qaly_loss_per_eligible_person"][0] = (
            0.2 * item["health_impact"]["qaly_loss_per_occurrence"]
        )
        with self.assertRaisesRegex(ModelValidationError, "exceeds one model cycle"):
            validate_event_disutilities(
                inputs[0], inputs[1], inputs[10], inputs[11], artifact, b"changed"
            )

    def test_rejects_combined_utility_below_anchor(self) -> None:
        inputs = event_disutility_inputs()
        artifact = copy.deepcopy(inputs[12])
        item = artifact["items"]["intervention-treatment-burden"]
        item["health_impact"]["utility_decrement"] = 2.0
        item["cycle_qaly_loss_per_eligible_person"] = [2.0, 1.0]
        artifact["cycle_state_qaly_losses"]["intervention"][0][0] += 1.98
        artifact["cycle_state_qaly_losses"]["intervention"][1][0] += 0.99
        with self.assertRaisesRegex(ModelValidationError, "below -1"):
            validate_event_disutilities(
                inputs[0], inputs[1], inputs[10], inputs[11], artifact, b"changed"
            )


if __name__ == "__main__":
    unittest.main()
