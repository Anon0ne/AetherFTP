"""Read local folders without allowing an inaccessible child to hide siblings."""
from pathlib import Path
import os
import stat


def navigation_path(path):
    """Resolve only the current user's legacy My Documents junction."""
    path = Path(path).expanduser().absolute()
    if os.name != 'nt':
        return path
    try:
        relative = path.relative_to(Path.home())
    except ValueError:
        return path
    if not relative.parts or relative.parts[0].casefold() != 'my documents':
        return path
    alias = Path.home() / relative.parts[0]
    junction = getattr(alias, 'is_junction', lambda: (
        getattr(alias.lstat(), 'st_reparse_tag', None) == 0xA0000003))()
    if not junction:
        return path
    target = str(alias.readlink())
    if target.startswith('\\\\?\\UNC\\'):
        target = '\\\\' + target[8:]
    elif target.startswith('\\\\?\\'):
        target = target[4:]
    target = Path(target)
    if not target.is_absolute():
        target = alias.parent / target
    return target.joinpath(*relative.parts[1:])


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
