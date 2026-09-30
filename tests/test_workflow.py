"""Synthetic-data checks; no patient-derived labels are used."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from prostate_mri.audit import audit
from prostate_mri.features import build_features
from prostate_mri.modeling import evaluate_external, grouped_development_evaluation, train


class AuditTests(unittest.TestCase):
    def test_counts_and_summary_mismatch_detection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for region in ("Lesion_PZ", "Lesion_CG", "Healthy_PZ", "Healthy_CG"):
                (root / region).mkdir()
                (root / region / "P1.csv").write_text("Map,Unit,Value\nADC,u,1\n", encoding="utf-8")
            summary = root / "P1_region_summary.csv"
            summary.write_text(
                "PatientID,Region,Map,Unit,N,Mean,Std,Median,Min,Max\n"
                + "".join(f"P1,{region},ADC,u,1,1,0,1,1,1\n" for region in
                          ("Lesion_PZ", "Lesion_CG", "Healthy_PZ", "Healthy_CG")),
                encoding="utf-8",
            )
            report = audit(root)
            self.assertEqual(report["measurement_count"], 4)
            self.assertEqual(report["summary_count_mismatches"], [])
            summary.write_text(summary.read_text(encoding="utf-8").replace("Lesion_PZ,ADC,u,1", "Lesion_PZ,ADC,u,2"), encoding="utf-8")
            self.assertEqual(len(audit(root)["summary_count_mismatches"]), 1)


class FeatureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.summary = pd.DataFrame([
            {"PatientID": "P1", "Region": region, "Map": map_name, "N": 25, "Median": median}
            for region, map_name, median in (
                ("Lesion_CG", "ADC", 900), ("Healthy_CG", "ADC", 1500),
                ("Lesion_CG", "T2", 40), ("Healthy_CG", "T2", 50),
            )
        ])
        self.linkage = pd.DataFrame([{
            "patient_id": "P1", "lesion_id": "L1", "region": "Lesion_CG",
            "pathology_label": 1, "roi_to_lesion_match": True,
        }])

    def test_ratios_and_match_guard(self) -> None:
        result = build_features(self.summary, self.linkage)
        self.assertAlmostEqual(result.loc[0, "adc_ratio"], 0.6)
        self.assertAlmostEqual(result.loc[0, "t2_ratio"], 0.8)
        ambiguous = pd.concat([self.linkage, self.linkage.assign(lesion_id="L2")], ignore_index=True)
        with self.assertRaisesRegex(ValueError, "Multiple lesions"):
            build_features(self.summary, ambiguous)

    def test_unconfirmed_match_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "explicitly confirmed"):
            build_features(self.summary, self.linkage.assign(roi_to_lesion_match=False))


class ModelingTests(unittest.TestCase):
    @staticmethod
    def synthetic_frame(start: int, stop: int) -> pd.DataFrame:
        return pd.DataFrame([
            {
                "patient_id": f"S{patient}", "lesion_id": f"L{label}", "pathology_label": label,
                "adc_ratio": 1.05 - 0.35 * label + 0.01 * patient,
                "t2_ratio": 1.02 - 0.25 * label + 0.005 * patient,
                "zone_cg": patient % 2,
            }
            for patient in range(start, stop) for label in (0, 1)
        ])

    def test_patient_grouped_pilot_and_external_overlap_guard(self) -> None:
        development = self.synthetic_frame(0, 8)
        report, predictions = grouped_development_evaluation(development)
        self.assertEqual(report["patient_count"], 8)
        self.assertEqual(len(predictions), 16)
        for model in ("logistic_regression", "knn", "decision_tree"):
            self.assertTrue(predictions[f"{model}_probability"].between(0, 1).all())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            train(development, root / "model", "Synthetic pathology-positive lesion")
            manifest = json.loads((root / "model" / "model_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["training_patient_ids"]), 8)
            with self.assertRaisesRegex(ValueError, "development patient"):
                evaluate_external(development.iloc[:2], root / "model", root / "invalid")
            external = self.synthetic_frame(8, 10)
            result = evaluate_external(external, root / "model", root / "external")
            self.assertEqual(result["patient_count"], 2)

    def test_three_patient_cohort_cannot_run_pilot(self) -> None:
        with self.assertRaisesRegex(ValueError, "independent patients"):
            grouped_development_evaluation(self.synthetic_frame(0, 3))


if __name__ == "__main__":
    unittest.main()
