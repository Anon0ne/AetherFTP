"""Expand local folders without following links or junctions."""
import os
from pathlib import Path
import posixpath
from file_filters import FileFilter


def is_link(path):
    return path.is_symlink() or getattr(path, 'is_junction', lambda: False)()


def plan_uploads(paths, remote_directory, file_filter=None):
    file_filter = file_filter or FileFilter()
    directories, files, skipped = [], [], 0
    seen_dirs, seen_files = set(), set()
    def add_directory(remote):
        if remote not in seen_dirs:
            seen_dirs.add(remote); directories.append(remote)
    def add_file(local, remote):
        if remote in seen_files:
            raise ValueError('Multiple selected files have the same remote destination')
        seen_files.add(remote); files.append((str(local), remote))
    def fail(error):
        raise error
    for source in paths:
        source = Path(source)
        if is_link(source):
            skipped += 1; continue
        if not source.name:
            raise ValueError('Select a named folder instead of a filesystem root')
        if not file_filter.allows(source.name, directory=source.is_dir()):
            skipped += 1; continue
        target = posixpath.join(remote_directory, source.name)
        if source.is_file():
            add_file(source, target)
        elif source.is_dir():
            add_directory(target)
            for root, subdirs, names in os.walk(source, followlinks=False, onerror=fail):
                root = Path(root)
                relative = root.relative_to(source).parts
                remote = posixpath.join(target, *relative)
                subdirs.sort(); names.sort()
                for name in subdirs[:]:
                    child = root / name
                    if is_link(child) or not file_filter.allows(name, child.relative_to(source).as_posix(), directory=True):
                        skipped += 1; subdirs.remove(name)
                    else: add_directory(posixpath.join(remote, name))
                for name in names:
                    child = root / name
                    if is_link(child) or not file_filter.allows(name, child.relative_to(source).as_posix()): skipped += 1
                    elif child.is_file(): add_file(child, posixpath.join(remote, name))
                    else: raise ValueError('Unsupported local filesystem entry')
        else:
            raise FileNotFoundError('Selected upload source does not exist')
    return directories, files, skipped
