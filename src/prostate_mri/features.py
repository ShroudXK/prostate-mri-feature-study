"""Build one pathology-linked feature row per MRI lesion when linkage is verified."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from prostate_mri.explore import MIN_REGION_VALUES, load_summary

REQUIRED_LINKAGE = {"patient_id", "lesion_id", "region", "pathology_label", "roi_to_lesion_match"}
MODEL_FEATURES = ["adc_ratio", "t2_ratio", "zone_cg"]


def build_features(summary: pd.DataFrame, linkage: pd.DataFrame) -> pd.DataFrame:
    missing = REQUIRED_LINKAGE - set(linkage.columns)
    if missing:
        raise ValueError(f"Linkage table missing columns: {sorted(missing)}")
    if linkage.empty:
        raise ValueError("Linkage table has no lesion rows")
    if linkage.duplicated(["patient_id", "lesion_id"]).any():
        raise ValueError("Duplicate patient-lesion identifiers")
    if linkage.duplicated(["patient_id", "region"]).any():
        raise ValueError("Multiple lesions map to one aggregated region export; obtain lesion-specific MRI features")
    if not linkage["region"].isin(["Lesion_PZ", "Lesion_CG"]).all():
        raise ValueError("Only lesion regions may receive pathology labels")
    labels = pd.to_numeric(linkage["pathology_label"], errors="coerce")
    if labels.isna().any() or not labels.isin([0, 1]).all():
        raise ValueError("pathology_label must be 0 (negative) or 1 (positive) for every row")
    matches = linkage["roi_to_lesion_match"].astype(str).str.lower().isin(["true", "1", "yes"])
    if not matches.all():
        raise ValueError("Every ROI-to-lesion match must be explicitly confirmed")

    indexed = summary.set_index(["PatientID", "Region", "Map"])
    rows = []
    for item in linkage.itertuples(index=False):
        patient, region = str(item.patient_id), str(item.region)
        zone = region.split("_", 1)[1]
        values = {}
        for map_name in ("ADC", "T2"):
            lesion_key = (patient, region, map_name)
            healthy_key = (patient, f"Healthy_{zone}", map_name)
            if lesion_key not in indexed.index or healthy_key not in indexed.index:
                raise ValueError(f"Missing {map_name} summary for {patient} {region}")
            lesion, healthy = indexed.loc[lesion_key], indexed.loc[healthy_key]
            if int(lesion["N"]) < MIN_REGION_VALUES or int(healthy["N"]) < MIN_REGION_VALUES:
                raise ValueError(f"Insufficient {map_name} measurements for {patient} {region}")
            if pd.isna(lesion["Median"]) or pd.isna(healthy["Median"]) or float(healthy["Median"]) <= 0:
                raise ValueError(f"Invalid {map_name} median for {patient} {region}")
            values[f"{map_name.lower()}_ratio"] = float(lesion["Median"]) / float(healthy["Median"])
        rows.append({
            "patient_id": patient,
            "lesion_id": str(item.lesion_id),
            "pathology_label": int(item.pathology_label),
            "zone_cg": int(zone == "CG"),
            **values,
        })
    return pd.DataFrame(rows, columns=["patient_id", "lesion_id", "pathology_label", *MODEL_FEATURES])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path.cwd())
    parser.add_argument("--linkage", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("outputs/lesion_features.csv"))
    args = parser.parse_args()
    summary = load_summary(args.data_dir)
    linkage = pd.read_csv(args.linkage)
    result = build_features(summary, linkage)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False)
    print(f"Built {len(result)} pathology-linked lesion rows from {result.patient_id.nunique()} patients")
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
