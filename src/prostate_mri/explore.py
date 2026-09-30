"""Make descriptive, paired MRI-region comparisons from the summary CSVs."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

MIN_REGION_VALUES = 20  # Descriptive display rule, not a clinical threshold.


def load_summary(data_dir: Path) -> pd.DataFrame:
    files = sorted(data_dir.glob("P*_region_summary.csv"))
    if not files:
        raise ValueError(f"No patient summary CSV files found in {data_dir}")
    frame = pd.concat((pd.read_csv(path) for path in files), ignore_index=True)
    required = {"PatientID", "Region", "Map", "Unit", "N", "Median"}
    if not required.issubset(frame.columns):
        raise ValueError(f"Summary CSV missing columns: {sorted(required - set(frame.columns))}")
    if frame.duplicated(["PatientID", "Region", "Map"]).any():
        raise ValueError("Duplicate patient-region-map summary rows")
    return frame


def paired_contrasts(summary: pd.DataFrame, min_values: int = MIN_REGION_VALUES) -> pd.DataFrame:
    rows = []
    for (patient, map_name), group in summary.groupby(["PatientID", "Map"]):
        index = group.set_index("Region")
        for zone in ("PZ", "CG"):
            lesion_key, healthy_key = f"Lesion_{zone}", f"Healthy_{zone}"
            if lesion_key not in index.index or healthy_key not in index.index:
                continue
            lesion, healthy = index.loc[lesion_key], index.loc[healthy_key]
            if int(lesion["N"]) < min_values or int(healthy["N"]) < min_values:
                continue
            lesion_median, healthy_median = float(lesion["Median"]), float(healthy["Median"])
            if pd.isna(lesion_median) or pd.isna(healthy_median):
                continue
            rows.append({
                "patient_id": patient,
                "zone": zone,
                "map": map_name,
                "unit": lesion["Unit"],
                "lesion_n": int(lesion["N"]),
                "healthy_n": int(healthy["N"]),
                "lesion_median": lesion_median,
                "healthy_median": healthy_median,
                "difference": lesion_median - healthy_median,
                "ratio": lesion_median / healthy_median if healthy_median else float("nan"),
            })
    return pd.DataFrame(rows)


def make_figure(contrasts: pd.DataFrame, output: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10, 5.2), layout="constrained")
    for ax, map_name, unit in zip(axes, ("ADC", "T2"), (r"$10^{-6}$ mm$^2$/s", "ms")):
        subset = contrasts[contrasts["map"] == map_name].sort_values(["patient_id", "zone"])
        if subset.empty:
            ax.text(0.5, 0.5, "No eligible pairs", ha="center", va="center", transform=ax.transAxes)
            continue
        for row in subset.itertuples(index=False):
            ax.plot([0, 1], [row.healthy_median, row.lesion_median], color="#718096", lw=1.5, zorder=1)
            ax.scatter([0], [row.healthy_median], color="#277da1", s=48, zorder=2)
            ax.scatter([1], [row.lesion_median], color="#d1495b", s=48, zorder=2)
            ax.annotate(f"{row.patient_id} {row.zone}", (1, row.lesion_median), xytext=(6, 0),
                        textcoords="offset points", va="center", fontsize=8)
        ax.set_xlim(-0.2, 1.5)
        ax.set_xticks([0, 1], ["Annotated healthy", "Lesion"])
        ax.set_ylabel(f"Median {map_name} ({unit})")
        ax.set_title(map_name)
        ax.grid(axis="y", alpha=0.2)
    fig.suptitle("Within-patient, same-zone MRI contrasts\nExploratory region comparison, not a pathology-based cancer test", fontsize=12)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)


def write_report(contrasts: pd.DataFrame, output: Path) -> None:
    eligible = contrasts[contrasts["map"].isin(["ADC", "T2"])]
    pair_maps = eligible.groupby(["patient_id", "zone"])["map"].nunique()
    pairs = pair_maps[pair_maps == 2]
    lines = [
        "# Exploratory MRI-region results",
        "",
        "These results compare annotated lesion and healthy tissue within the same patient and zone.",
        "They do not estimate cancer-diagnosis performance. Individual map values within a patient are repeated measurements.",
        "",
        f"Eligible patient-zone pairs for ADC/T2: **{len(pairs)}** (minimum {MIN_REGION_VALUES} values per region-map).",
        "",
        "| Map | Eligible pairs | Lesion median lower than healthy | Median lesion-minus-healthy difference |",
        "| --- | ---: | ---: | ---: |",
    ]
    for map_name in ("ADC", "T2"):
        sub = contrasts[contrasts["map"] == map_name]
        if len(sub):
            lines.append(f"| {map_name} | {len(sub)} | {int((sub['difference'] < 0).sum())} | {sub['difference'].median():.1f} {sub['unit'].iloc[0]} |")
    lines += [
        "",
        "The sample consists of three patients; these contrasts are descriptive and may reflect the image-based annotation process.",
        "The P2 peripheral-zone lesion is absent. The P3 peripheral-zone lesion has only four T2W values and is excluded by the display rule.",
        "No significance test, diagnostic accuracy, or population-level effect estimate is claimed.",
        "",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    args = parser.parse_args()
    contrasts = paired_contrasts(load_summary(args.data_dir))
    if contrasts.empty:
        raise ValueError("No eligible same-zone contrasts")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    contrasts.to_csv(args.output_dir / "paired_contrasts.csv", index=False)
    make_figure(contrasts, args.output_dir / "adc_t2_paired.png")
    write_report(contrasts, args.output_dir / "exploratory_results.md")
    print(f"Saved exploratory results in {args.output_dir}")


if __name__ == "__main__":
    main()
