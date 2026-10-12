"""Private paired bookmarks, bounded path mapping, and verified remote edits."""
import hashlib
import json
import os
from pathlib import Path
import posixpath
import shutil
import tempfile
from server_book import STORE

BOOKMARKS = STORE.parent / 'bookmarks.json'


def validate_remote_name(name):
    if not name or name in ('.', '..') or name.endswith((' ', '.')) or Path(name).is_reserved() or any(
            c in name for c in '<>:"/\\|?*') or any(ord(c) < 32 for c in name):
        raise ValueError('Enter a valid filename without path separators or reserved characters')
    return name


def create_remote_file(client, local, remote, progress):
    if client.kind == 'SFTP':
        # Exclusive creation prevents replacing another user's existing file.
        with client.conn.open(remote, 'wx'):
            pass
        progress(0, 0)
    else:
        name = posixpath.basename(remote)
        if any(entry[0].casefold() == name.casefold() for entry in client.listdir(posixpath.dirname(remote) or '/')):
            raise FileExistsError('A file or folder with that name already exists')
        client.upload(local, remote, progress, resume=False)


def server_scope(args):
    host, port, user, _password, protocol = args
    return hashlib.sha256(json.dumps([host.casefold(), port, user, protocol]).encode()).hexdigest()


def load_bookmarks():
    try:
        records = json.loads(BOOKMARKS.read_text(encoding='utf-8'))
        if not isinstance(records, list): return []
        return [r for r in records if isinstance(r, dict) and
                set(r) == {'name', 'scope', 'local', 'remote'} and
                all(isinstance(v, str) and v for v in r.values())]
    except (OSError, ValueError): return []


def save_bookmarks(records):
    if not isinstance(records, list) or any(not isinstance(r, dict) or
            set(r) != {'name', 'scope', 'local', 'remote'} or
            not all(isinstance(v, str) and v for v in r.values()) for r in records):
        raise ValueError('Invalid paired bookmarks')
    BOOKMARKS.parent.mkdir(parents=True, exist_ok=True)
    temp = BOOKMARKS.with_suffix('.tmp')
    temp.write_text(json.dumps(records, indent=2), encoding='utf-8')
    os.replace(temp, BOOKMARKS)


def paired_paths(local_root, remote_root, side, target):
    local_root = Path(local_root).resolve()
    remote_root = posixpath.normpath(remote_root)
    if side == 'local':
        local = Path(target).resolve()
        parts = local.relative_to(local_root).parts
        return local, posixpath.join(remote_root, *parts) if parts else remote_root
    remote = posixpath.normpath(target)
    relative = posixpath.relpath(remote, remote_root)
    if relative == '..' or relative.startswith('../'):
        raise ValueError('Synchronized browsing cannot leave its root folders')
    parts = () if relative == '.' else relative.split('/')
    if any('\\' in p or ':' in p for p in parts): raise ValueError('Unsafe paired local path')
    local = local_root.joinpath(*parts).resolve()
    local.relative_to(local_root)
    return local, remote


def digest(path):
    with open(path, 'rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()


class RemoteEdit:
    def __init__(self, remote, folder=None):
        self.remote = remote
        name = posixpath.basename(remote)
        if not name or name in ('.', '..') or name.endswith((' ', '.')) or Path(name).is_reserved() or any(c in name for c in '<>:"\\|?*\x00'):
            raise ValueError('Unsafe remote filename')
        self.temp = tempfile.TemporaryDirectory(prefix='aetherftp-edit-', dir=folder)
        self.path = Path(self.temp.name) / name
        self.work = Path(self.temp.name) / '.aether-work'; self.work.mkdir()
        if self.path == self.work:
            self.temp.cleanup(); raise ValueError('Reserved editing filename')
        self.original_hash = None
        self.last_stamp = None

    def stamp(self):
        stat = self.path.stat()
        return stat.st_mtime_ns, stat.st_size

    def download(self, client, progress=None):
        client.download(self.remote, str(self.path), progress or (lambda *_: None), resume=False)
        self.original_hash = digest(self.path)
        self.last_stamp = self.stamp()

    def upload_changes(self, client, progress=None, verify_progress=None):
        # Upload a snapshot so saves in the editor cannot mutate a transfer midstream.
        snapshot = self.work / 'upload'
        check = self.work / 'remote'
        shutil.copyfile(self.path, snapshot)
        changed_hash = digest(snapshot)
        if changed_hash == self.original_hash: return False
        client.download(self.remote, str(check), verify_progress or (lambda *_: None), resume=False)
        if digest(check) != self.original_hash:
            raise RuntimeError('Remote file changed since editing began; changes were not uploaded. Start a new edit to reconcile them.')
        client.upload(str(snapshot), self.remote, progress or (lambda *_: None), resume=False)
        self.original_hash = changed_hash
        return True

    def close(self):
        self.temp.cleanup()
