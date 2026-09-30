"""Patient-grouped development evaluation and locked external evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    confusion_matrix,
    roc_auc_score,
)
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

from prostate_mri.features import MODEL_FEATURES

MIN_PILOT_PATIENTS = 6  # Software floor for a demonstration, not a sample-size adequacy claim.


def load_feature_table(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {"patient_id", "lesion_id", "pathology_label", *MODEL_FEATURES}
    if not required.issubset(frame.columns):
        raise ValueError(f"Missing feature columns: {sorted(required - set(frame.columns))}")
    if frame.duplicated(["patient_id", "lesion_id"]).any():
        raise ValueError("Duplicate lesion rows")
    if frame[MODEL_FEATURES].isna().any().any():
        raise ValueError("Missing model features; investigate MRI export before modeling")
    if not frame["pathology_label"].isin([0, 1]).all():
        raise ValueError("pathology_label must be 0 or 1")
    return frame


def estimators() -> dict:
    return {
        "logistic_regression": make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                                             LogisticRegression(C=1.0, class_weight="balanced", max_iter=1000)),
        "knn": make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                             KNeighborsClassifier(n_neighbors=3)),
        "decision_tree": make_pipeline(SimpleImputer(strategy="median"),
                                       DecisionTreeClassifier(max_depth=2, min_samples_leaf=3,
                                                              class_weight="balanced", random_state=42)),
    }


def metrics(y_true: np.ndarray, probabilities: np.ndarray) -> dict:
    predictions = (probabilities >= 0.5).astype(int)
    matrix = confusion_matrix(y_true, predictions, labels=[0, 1])
    result = {
        "n_lesions": int(len(y_true)),
        "class_counts": {"negative": int((y_true == 0).sum()), "positive": int((y_true == 1).sum())},
        "confusion_matrix_rows_actual_0_1": matrix.tolist(),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, predictions)),
        "sensitivity": float(matrix[1, 1] / matrix[1].sum()) if matrix[1].sum() else None,
        "specificity": float(matrix[0, 0] / matrix[0].sum()) if matrix[0].sum() else None,
    }
    if len(np.unique(y_true)) == 2:
        result["roc_auc"] = float(roc_auc_score(y_true, probabilities))
        result["average_precision"] = float(average_precision_score(y_true, probabilities))
    else:
        result["roc_auc"] = None
        result["average_precision"] = None
    return result


def grouped_development_evaluation(frame: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    groups = frame["patient_id"].astype(str).to_numpy()
    if len(np.unique(groups)) < MIN_PILOT_PATIENTS:
        raise ValueError(
            f"Only {len(np.unique(groups))} independent patients; pilot modeling requires at least "
            f"{MIN_PILOT_PATIENTS} for this software workflow, and that floor does not establish study adequacy"
        )
    x = frame[MODEL_FEATURES].to_numpy(dtype=float)
    y = frame["pathology_label"].to_numpy(dtype=int)
    if len(np.unique(y)) != 2:
        raise ValueError("Both pathology classes are required")
    splits = list(LeaveOneGroupOut().split(x, y, groups))
    for train, test in splits:
        if len(np.unique(y[train])) != 2:
            raise ValueError(f"Training patients lack both classes when holding out {groups[test[0]]}")
    results = {}
    predictions = frame[["patient_id", "lesion_id", "pathology_label"]].copy()
    for name, estimator in estimators().items():
        probabilities = np.full(len(frame), np.nan)
        for train, test in splits:
            estimator.fit(x[train], y[train])
            probabilities[test] = estimator.predict_proba(x[test])[:, 1]
        if np.isnan(probabilities).any():
            raise RuntimeError("A held-out lesion did not receive a prediction")
        predictions[f"{name}_probability"] = probabilities
        results[name] = metrics(y, probabilities)
    report = {
        "evaluation_type": "internal leave-one-patient-out pilot; not external validation",
        "patient_count": int(len(np.unique(groups))),
        "feature_names": MODEL_FEATURES,
        "threshold": 0.5,
        "models": results,
        "interpretation": "Exploratory internal estimates only. No model was selected from these scores; logistic regression is the prespecified primary model.",
    }
    return report, predictions


def train(frame: pd.DataFrame, output_dir: Path, outcome_definition: str) -> None:
    if not outcome_definition.strip():
        raise ValueError("A prespecified pathology outcome definition is required")
    report, predictions = grouped_development_evaluation(frame)
    output_dir.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(output_dir / "internal_predictions.csv", index=False)
    (output_dir / "internal_evaluation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    primary = estimators()["logistic_regression"]
    primary.fit(frame[MODEL_FEATURES].to_numpy(dtype=float), frame["pathology_label"].to_numpy(dtype=int))
    joblib.dump(primary, output_dir / "locked_logistic_model.joblib")
    manifest = {
        "feature_names": MODEL_FEATURES,
        "threshold": 0.5,
        "training_patient_ids": sorted(frame["patient_id"].astype(str).unique().tolist()),
        "outcome_definition": outcome_definition.strip(),
        "note": "Model and manifest are private patient-derived artifacts. Freeze both before new-patient evaluation.",
    }
    (output_dir / "model_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def evaluate_external(frame: pd.DataFrame, model_dir: Path, output_dir: Path) -> dict:
    manifest = json.loads((model_dir / "model_manifest.json").read_text(encoding="utf-8"))
    if set(frame["patient_id"].astype(str)) & set(manifest["training_patient_ids"]):
        raise ValueError("External data contain a development patient")
    if list(manifest["feature_names"]) != MODEL_FEATURES:
        raise ValueError("External feature schema does not match the model")
    model = joblib.load(model_dir / "locked_logistic_model.joblib")
    y = frame["pathology_label"].to_numpy(dtype=int)
    probabilities = model.predict_proba(frame[MODEL_FEATURES].to_numpy(dtype=float))[:, 1]
    report = {
        "evaluation_type": "independent new-patient evaluation",
        "patient_count": int(frame["patient_id"].nunique()),
        "outcome_definition": manifest["outcome_definition"],
        **metrics(y, probabilities),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "external_evaluation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    predictions = frame[["patient_id", "lesion_id", "pathology_label"]].copy()
    predictions["probability"] = probabilities
    predictions.to_csv(output_dir / "external_predictions.csv", index=False)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    dev = subparsers.add_parser("develop", help="Run grouped internal pilot evaluation and fit the prespecified model")
    dev.add_argument("--features", type=Path, required=True)
    dev.add_argument("--output-dir", type=Path, default=Path("outputs/model"))
    dev.add_argument("--outcome-definition", required=True,
                     help="Exact pathology outcome, fixed before model development")
    external = subparsers.add_parser("external", help="Evaluate a frozen model on new patients")
    external.add_argument("--features", type=Path, required=True)
    external.add_argument("--model-dir", type=Path, required=True)
    external.add_argument("--output-dir", type=Path, default=Path("outputs/external"))
    args = parser.parse_args()
    frame = load_feature_table(args.features)
    if args.command == "develop":
        train(frame, args.output_dir, args.outcome_definition)
        print(f"Saved internal pilot evaluation and locked model in {args.output_dir}")
    else:
        report = evaluate_external(frame, args.model_dir, args.output_dir)
        print(f"Evaluated {report['patient_count']} independent new patients; saved {args.output_dir}")


if __name__ == "__main__":
    main()
