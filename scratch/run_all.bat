set PYTHONPATH=.
python scratch\delete_fallbacks.py
python scripts\populate_cache.py "Breast cancer"
python scripts\populate_cache.py "Ovarian cancer"
python scripts\populate_cache.py "Uterine cancer"
python export_exposures_dietary.py
