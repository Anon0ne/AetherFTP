"""Read local folders without allowing an inaccessible child to hide siblings."""
from pathlib import Path
import stat


def read_directory(path):
    path = Path(path)
    entries = []
    skipped = 0
    for child in path.iterdir():
        try:
            info = child.stat()
        except OSError:
            skipped += 1
            continue
        entries.append((child.name, stat.S_ISDIR(info.st_mode), info.st_size, str(child)))
    entries.sort(key=lambda entry: (not entry[1], entry[0].casefold()))
    return [('..', True, 0, str(path.parent))] + entries, skipped
