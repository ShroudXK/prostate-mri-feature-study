# Data dictionary and pathology linkage

## Available MRI export

| Field | Meaning | Current location |
| --- | --- | --- |
| `PatientID` | De-identified patient key (`P1`–`P3`) | Summary CSV files; inferred from raw CSV filenames |
| `Region` | `Lesion_PZ`, `Lesion_CG`, `Healthy_PZ`, or `Healthy_CG` | Summary CSV files; inferred from raw CSV parent folders |
| `Map` | `ADC`, `T1`, `T2`, `PBF`, or `T2W` | All CSV files |
| `Unit` | Exported measurement unit; varies by map | All CSV files |
| `Value` | One exported map value | Region CSV files |
| `N`, `Mean`, `Std`, `Median`, `Min`, `Max` | Descriptive statistics for a patient, region, and map | Summary CSV files |

The raw export has no lesion identifier, voxel coordinate, or key aligning values across maps. `N` counts measurements, not patients or lesions. A blank or nearly blank region requires source review before analysis.

## Private pathology linkage required before modeling

Maintain a separate, access-controlled table with at least these fields:

| Field | Purpose |
| --- | --- |
| `patient_id` | Joins to the de-identified MRI patient key |
| `lesion_id` | Stable identifier for the individual MRI lesion |
| `mri_region` | Zone and region file associated with this lesion |
| `roi_to_lesion_match` | Explicit confirmation that the MRI export represents this lesion only |
| `pathology_result` | Positive, negative, or indeterminate, using a documented definition |
| `isup_grade_group` | Grade group, if available; retain missingness explicitly |
| `reference_standard` | Targeted biopsy, systematic biopsy, prostatectomy, or other documented method |
| `mri_to_pathology_days` | Interval between imaging and pathology |
| `matching_notes` | Ambiguity, multiple lesions in one region, or exclusions |

If several lesions were pooled into a single region file, obtain lesion-specific MRI features before lesion-level modeling. Do not copy a patient-level result to all lesion rows or assign a pathology label to annotated healthy tissue without lesion-specific evidence.
