# Study protocol

## Motivation and question

Quantitative prostate MRI produces many measurements per person, but the number of independent patients determines whether a model can generalize. This project first characterizes lesion-to-tissue MRI contrasts, then prepares a pathology-linked lesion model designed for evaluation on unseen patients.

**Primary future question:** Can a small, prespecified set of lesion-level MRI features discriminate a defined pathology outcome in patients not used for model development?

**Current question:** How do ADC and T2 medians in annotated lesions compare with annotated healthy tissue from the same patient and anatomical zone?

The current question concerns MRI annotations and does not establish whether a lesion is malignant. Source imaging, pathology labels, and future data are needed for the primary question.

## Data and units

- Current cohort: P1–P3; independent evaluation group: patient.
- Raw export row: one value from a single MRI map. Rows across maps have no alignment key.
- Exploratory comparison unit: one patient-zone-map pair with both lesion and healthy region summaries.
- Future prediction unit: one MRI lesion with an unambiguous lesion-level pathology match.
- Region labels and pathology labels must remain distinct.

## Exploratory analysis rules

This protocol was written after an initial data audit and is not preregistered. Use region medians from the existing summaries. Include a patient-zone-map pair in the display if both the lesion and healthy region have at least 20 values. Plot ADC and T2 as the main descriptive maps because they have usable same-zone pairs; report differences and counts without a significance test or diagnostic accuracy estimate. The 20-value display rule is a data-quality convention, not evidence of sample-size adequacy.

## Pathology linkage gate

Before modeling, verify patient ID, lesion ID, zone, source ROI, and reference-standard result. A single aggregated ROI must not be assigned to multiple pathology lesions. Resolve indeterminate pathology and MRI-to-pathology time interval in the study protocol. Define `pathology_label=1` and `=0` precisely, including whether the target is any cancer or clinically significant cancer. Do not use annotated healthy tissue as pathology-negative lesions.

## Planned pilot models

The planned feature set, fixed before pathology-linked fitting, is the lesion-to-same-zone-healthy median ratio for ADC and T2, plus a CG indicator. This reduces patient-level scale differences without attempting to align raw values across maps. PBF and T2W remain exploratory because the present export has few PBF values in some lesions and T2W is in arbitrary units. A feature or map can be added only through a documented protocol revision made before evaluating new patients.

The primary model is regularized logistic regression. KNN with three neighbors and a shallow decision tree are secondary benchmarks. All imputation and scaling take place inside each training fold. This is a technical pilot, not a clinically validated model. A six-patient software floor prevents running the pilot on the current three-person cohort; an appropriate research sample size requires a separate outcome- and precision-based plan.

## Evaluation

During development, leave one patient out at a time; all lesions from that person remain held out together. Compare all three prespecified models using out-of-fold predictions. The threshold is fixed at 0.5 for the pilot. Report class counts, confusion matrix, sensitivity, specificity, balanced accuracy, ROC-AUC, and average precision when defined. Model comparison is descriptive; the primary model is not selected from these scores.

Fit the prespecified primary model using all development patients and freeze its features, threshold, and outcome definition. Only then evaluate data from entirely new patients. The external evaluator rejects any patient ID that appears in the development manifest. Results from new patients will be reported separately with uncertainty intervals and subgroup analysis when enough independent cases permit them.

## Current limitations and interpretation

Three patients cannot support a reliable estimate of cancer-prediction performance. The independent outcome labels are held separately, and a lesion-to-ROI match has not been verified in the source files. Missing peripheral-zone lesion exports and values at map boundaries require source review. Any observed lesion-to-tissue contrast may partly reflect how the MRI regions were annotated. No result from this dataset alone should be presented as evidence of clinical diagnostic utility.

## Reporting and sharing

Report development and evaluation transparently using [TRIPOD+AI](https://www.bmj.com/content/385/bmj-2023-078378) and review risk of bias with [PROBAST+AI](https://www.bmj.com/content/388/bmj-2024-082505). Publish code and schema. Share original or derived patient data only with confirmed permission and an appropriate disclosure review.
