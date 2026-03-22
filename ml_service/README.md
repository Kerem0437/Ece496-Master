# ML Service

This service now performs **per-feature gap-fill verification**.

## Model behavior

For each modeled variable:
- a dedicated model is trained for that variable alone
- **normal mode** keeps about 90% of raw points and predicts the missing 10%
- **strict mode** keeps about 75% of raw points and predicts the missing 25%
- suspiciousness is based on how far the predicted hidden points are from the true hidden points
- live review also includes **zero-drop protection** for monitored channels

## Clean retrain

Delete old artifacts if needed:

```bash
rm -f artifacts/model.pt artifacts/scaler.json artifacts/calibration.json
rm -rf artifacts/feature_models
rm -f artifacts/manifest.json
```

Then retrain:

```bash
python train.py --data-dir ../demo/data --epochs 12 --seq-len 60 --stride 10
```

## Run

```bash
uvicorn server:app --host 127.0.0.1 --port 8000
```

## Health

`GET /health` now reports:
- loaded per-feature models
- artifact version
- the keep fractions used for normal and strict review


## Truthful local demo report

After retraining, generate a local HTML report with training loss, confusion matrix, dataset scores, and raw/predicted overlays:

```bash
cd ../demo
python demo_onefile.py --out demo_report.html
python -m http.server 8765
```

Then open `http://127.0.0.1:8765/demo_report.html`.
