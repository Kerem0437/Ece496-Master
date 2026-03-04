# Master Variable List (Human Readable)

This document explains the project’s stable variable names (do not rename).
These names are used consistently across:
- Mock data: `lib/data/mockData.ts`
- UI pages: `app/experiments/*`
- Components: `components/*`
- Types: `lib/types.ts`

The idea: later (T6+), you can replace the mock data layer with DB/API calls, and keep the UI intact.

---

## Core identifiers
- `experiment_id`
  - What: Logical experiment/run grouping ID.
  - Found in: `lib/data/mockData.ts` (experiments array)
  - Used in: list table and detail route
  - Code: `app/experiments/ExperimentsClient.tsx`, `app/experiments/[experiment_id]/page.tsx`

- `measurement_id`
  - What: Unique measurement record ID within time-series data.
  - Found in: `lib/data/mockData.ts` (measurements array)
  - Used in: raw measurements table and chart x-order
  - Code: `app/experiments/[experiment_id]/page.tsx`

---

## Device & time fields
- `device_id`, `device_alias`
  - What: Physical device identifier and human-friendly label.
  - Found in: `lib/data/mockData.ts`
  - Used in: list + detail header + filters
  - Code: `app/experiments/ExperimentsClient.tsx`, `app/experiments/[experiment_id]/page.tsx`

- `timestamp_utc`
  - What: Timestamp for each measurement record (UTC string).
  - Found in: `lib/data/mockData.ts`
  - Used in: raw measurement table + chart
  - Code: `app/experiments/[experiment_id]/page.tsx`

- `start_timestamp_utc`, `end_timestamp_utc`
  - What: Experiment start/end timestamps. End may be null (ongoing).
  - Found in: `lib/data/mockData.ts`
  - Used in: list column + time filter + duration
  - Code: `app/experiments/ExperimentsClient.tsx`, `app/experiments/[experiment_id]/page.tsx`

- `time_offset_seconds`, `sample_index`
  - What: Time offset from experiment start and sample index within series.
  - Found in: `lib/data/mockData.ts`
  - Used in: chart x-axis and measurement table
  - Code: `app/experiments/[experiment_id]/page.tsx`, `components/ChartPlaceholder.tsx`

---

## Measurement fields
- `sensor_type`, `value`, `unit`
  - What: Sensor type (spectrometer, pH, temperature, etc.), numeric value, unit label.
  - Found in: `lib/data/mockData.ts`
  - Used in: list “sensor types involved”, chart lines, raw table
  - Code: `app/experiments/ExperimentsClient.tsx`, `components/ChartPlaceholder.tsx`

---

## Integrity / chain-of-custody fields
- `hash`, `signature`, `device_cert_id`, `integrity_status`, `source_file_id`
  - What: Custody metadata + derived integrity status (VALID/INVALID/UNKNOWN).
  - Found in: `lib/data/mockData.ts`
  - Used in: list pills + detail status card + warning banner condition
  - Code: `components/StatusPill.tsx`, `app/experiments/[experiment_id]/page.tsx`

---

## Experiment metadata fields
- `contaminant_type`, `pH_initial`, `light_intensity`, `temperature`, `site_location`, `data_source_type`
  - What: Experiment context fields (some optional).
  - Found in: `lib/data/mockData.ts`
  - Used in: detail metadata card + header
  - Code: `app/experiments/[experiment_id]/page.tsx`

---

## ML fields (LSTM outputs)
- `ml_version`, `anomaly_score`, `ml_flag`, `ml_timestamp_utc`, `prediction_curve`
  - What: ML model outputs and flags.
  - Found in: `lib/data/mockData.ts`
  - Used in: list pill + detail status card + optional predicted curve preview + warning banner condition
  - Code: `components/StatusPill.tsx`, `app/experiments/[experiment_id]/page.tsx`

---

## Derived UI-only fields (computed in frontend)
These are not stored in mock data; they are computed in `lib/utils.ts`.

- `experiment_duration_seconds`
- `freshness_minutes`
- `record_count`
- `value_min`, `value_max`, `value_mean`

Found/used in:
- `lib/utils.ts`
- `app/experiments/ExperimentsClient.tsx`
- `app/experiments/[experiment_id]/page.tsx`
