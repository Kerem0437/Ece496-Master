# INTEGRATION: ML (LSTM outputs) — T9

## Purpose
Formalize how the UI gets ML outputs (flags/scores/prediction curves) without embedding ML logic in UI.

## ML fields (master variables)
- `ml_flag`
- `anomaly_score`
- `ml_version`
- `prediction_curve`
- `ml_timestamp_utc`

## What is mock vs real
**Mock (NOW):**
- `MockMLProvider` reads these fields from `mockData.ts`.

**Real (LATER):**
- `HuggingFaceMLProvider` would call an ML service endpoint (e.g., Hugging Face space, VM-hosted service, or API gateway).
- The ML service could:
  - read from DB
  - run inference
  - write results back to DB
  - or return results directly per experiment

## “Turn it on” later
1) Create an ML service endpoint:
   - `GET /ml/summary?experiment_id=...`
2) Implement that endpoint to return ML summary with the master variables.
3) Update `HuggingFaceMLProvider` to call it.
4) Set `ML_PROVIDER_MODE=hf`.

## Code location
- Interface + providers: `lib/ml/mlProvider.ts`
- Current consumer:
  - `/app/experiments/[experiment_id]/page.tsx`
