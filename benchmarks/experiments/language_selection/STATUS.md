# Isolated language suitability experiment

This branch contains experiments only. The product baseline is commit
`234891619d7bed88ddf3fae37e7f3e1b14a808b6`; no product source, public README,
release or main-branch update is part of this experiment.

## In progress

- Build an independently recorded current C baseline.
- Profile representative ingestion and recall before choosing additional scope.
- Implement equivalent Rust native loops and a larger Rust computation stage.
- Implement Node kernels and account separately for Python/Node transport.
- Audit Unicode, dispatch guards, whole outputs, indexes and experiment design.
- Freeze final inputs, artifacts and schedules before formal measurements.

No language winner or production change has been approved by these development
files. Local diagnostic measurements and formal hosted results will be labeled
separately, and adverse or incomplete attempts will remain visible.
