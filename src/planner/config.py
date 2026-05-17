from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_YELP_DATASET_DIR = PROJECT_ROOT / "yelp_dataset"
DEFAULT_INTERIM_DIR = PROJECT_ROOT / "data" / "interim" / "city_subsets"
DEFAULT_CACHE_DIR = PROJECT_ROOT / "cache"
DEFAULT_ENV_FILES = [
    PROJECT_ROOT / ".env.local",
    PROJECT_ROOT / ".env",
]


def load_env_file() -> dict[str, str]:
    """Load simple KEY=VALUE pairs from .env.local or .env.

    The first existing file in DEFAULT_ENV_FILES wins. Existing process env can
    still override these values at the call site when desired.
    """
    for env_file in DEFAULT_ENV_FILES:
        if not env_file.exists():
            continue

        parsed: dict[str, str] = {}
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            parsed[key.strip()] = value.strip().strip('"').strip("'")
        return parsed
    return {}
