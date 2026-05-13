from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_YELP_DATASET_DIR = PROJECT_ROOT / "yelp_dataset"
DEFAULT_INTERIM_DIR = PROJECT_ROOT / "data" / "interim" / "city_subsets"

