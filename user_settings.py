"""Non-secret preferences stored separately from server profiles."""
import json
import math
import os
from server_book import STORE

SETTINGS = STORE.parent / 'settings.json'
DEFAULTS = {'uploads': 1, 'downloads': 1, 'upload_mbps': 0.0, 'download_mbps': 0.0}


def validate_settings(values):
    result = DEFAULTS.copy()
    for name in ('uploads', 'downloads'):
        value = values.get(name, result[name])
        if type(value) is not int or not 1 <= value <= 8: raise ValueError('Concurrency must be 1–8')
        result[name] = value
    for name in ('upload_mbps', 'download_mbps'):
        value = values.get(name, result[name])
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 10000:
            raise ValueError('Invalid bandwidth limit')
        result[name] = float(value)
    return result


def load_settings():
    try: return validate_settings(json.loads(SETTINGS.read_text(encoding='utf-8')))
    except (OSError, ValueError, TypeError, AttributeError): return DEFAULTS.copy()


def save_settings(values):
    values = validate_settings(values)
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    temp = SETTINGS.with_suffix('.tmp')
    try:
        temp.write_text(json.dumps(values, indent=2), encoding='utf-8')
        os.replace(temp, SETTINGS)
    finally:
        if temp.exists(): temp.unlink()
