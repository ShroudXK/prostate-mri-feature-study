"""Audit the supplied region-level CSV exports without altering them."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

REGIONS = ("Lesion_PZ", "Lesion_CG", "Healthy_PZ", "Healthy_CG")
MAPS = ("ADC", "T1", "T2", "PBF", "T2W")


def audit(data_dir: Path) -> dict:
    summary_files = sorted(data_dir.glob("P*_region_summary.csv"))
    if not summary_files:
        raise ValueError(f"No patient summary CSV files found in {data_dir}")

    patients = [path.stem.removesuffix("_region_summary") for path in summary_files]
    if len(set(patients)) != len(patients):
        raise ValueError("Duplicate patient summary identifiers")

    counts: Counter[tuple[str, str, str]] = Counter()
    zeros: Counter[tuple[str, str, str]] = Counter()
    invalid: Counter[tuple[str, str, str]] = Counter()
    units: dict[str, set[str]] = defaultdict(set)
    for patient in patients:
        for region in REGIONS:
            path = data_dir / region / f"{patient}.csv"
            if not path.exists():
                raise ValueError(f"Missing region file: {path}")
            with path.open(newline="", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle)
                if not {"Map", "Unit", "Value"}.issubset(reader.fieldnames or []):
                    raise ValueError(f"Unexpected columns in {path}")
                for row in reader:
                    map_name = row["Map"].strip()
                    if map_name not in MAPS:
                        raise ValueError(f"Unknown map {map_name!r} in {path}")
                    key = (patient, region, map_name)
                    counts[key] += 1
                    units[map_name].add(row["Unit"].strip())
                    try:
                        value = float(row["Value"])
                        if value != value or value in (float("inf"), float("-inf")):
                            invalid[key] += 1
                        elif value == 0:
                            zeros[key] += 1
                    except ValueError:
                        invalid[key] += 1

    mismatches = []
    summary_rows = 0
    for path in summary_files:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                summary_rows += 1
                key = (row["PatientID"], row["Region"], row["Map"])
                expected = int(row["N"])
                actual = counts[key]
                if expected != actual:
                    mismatches.append({"patient": key[0], "region": key[1], "map": key[2], "summary_n": expected, "raw_n": actual})

    table = [
        {
            "patient_id": patient,
            "region": region,
            "map": map_name,
            "n": counts[(patient, region, map_name)],
            "zero_count": zeros[(patient, region, map_name)],
            "invalid_count": invalid[(patient, region, map_name)],
        }
        for patient in patients
        for region in REGIONS
        for map_name in MAPS
    ]
    return {
        "patient_count": len(patients),
        "patients": patients,
        "region_file_count": len(patients) * len(REGIONS),
        "summary_file_count": len(summary_files),
        "summary_row_count": summary_rows,
        "measurement_count": sum(counts.values()),
        "map_counts": {map_name: sum(counts[(p, r, map_name)] for p in patients for r in REGIONS) for map_name in MAPS},
        "units_by_map": {map_name: sorted(units[map_name]) for map_name in MAPS},
        "summary_count_mismatches": mismatches,
        "region_map_counts": table,
    }


def write_audit_summary(report: dict, path: Path) -> None:
    lines = [
        "# MRI export audit",
        "",
        f"Independent patients: **{report['patient_count']}**. Raw region files: **{report['region_file_count']}**. "
        f"Summary files: **{report['summary_file_count']}**. Exported values: **{report['measurement_count']:,}**.",
        f"Raw-to-summary count mismatches: **{len(report['summary_count_mismatches'])}**.",
        "",
        "| Map | Values | Zeros | Zero percentage |",
        "| --- | ---: | ---: | ---: |",
    ]
    for map_name in MAPS:
        rows = [row for row in report["region_map_counts"] if row["map"] == map_name]
        zeros = sum(row["zero_count"] for row in rows)
        n = report["map_counts"][map_name]
        lines.append(f"| {map_name} | {n:,} | {zeros:,} | {100 * zeros / n:.1f}% |")
    lines.extend([
        "",
        "Region-map exports with fewer than 20 values:",
        "",
        "| Patient | Region | Map | Values |",
        "| --- | --- | --- | ---: |",
    ])
    for row in report["region_map_counts"]:
        if row["n"] < 20:
            lines.append(f"| {row['patient_id']} | {row['region']} | {row['map']} | {row['n']} |")
    lines.extend([
        "",
        "Zero values and boundary values require confirmation from the MRI export protocol before being treated as missing or invalid.",
        "Each value is a repeated measurement within a patient; the value count is not the sample size for patient-level prediction.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("outputs/audit.json"))
    args = parser.parse_args()
    report = audit(args.data_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_audit_summary(report, args.output.with_name("audit_summary.md"))
    print(f"Audited {report['patient_count']} patients and {report['measurement_count']:,} measurements")
    print(f"Summary count mismatches: {len(report['summary_count_mismatches'])}")
    print(f"Saved {args.output} and {args.output.with_name('audit_summary.md')}")


if __name__ == "__main__":
    main()
