cd $PSScriptRoot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python train.py --data-dir ..\demo\data --epochs 8 --seq-len 60 --stride 60
