from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent         # .../app
PATH_JSON_CROSSINGS_INFO = (BASE_DIR.parent / "data" / "config.json").resolve()