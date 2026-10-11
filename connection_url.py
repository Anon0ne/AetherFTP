"""Parse connection URLs without persisting embedded secrets."""
import posixpath
from urllib.parse import unquote, urlsplit


def parse_connection_url(value):
    if any(ord(c) < 32 for c in value):
        raise ValueError('Control characters are not allowed')
    url = urlsplit(value.strip())
    protocols = {'ftp': 'FTP', 'ftps': 'FTPS', 'ftpes': 'FTPES', 'sftp': 'SFTP'}
    if url.scheme.lower() not in protocols or not url.hostname:
        raise ValueError('Use an ftp, ftps, ftpes or sftp URL with a host')
    if url.password is not None:
        raise ValueError('Enter the password in the password field, not in a URL')
    if url.query or url.fragment:
        raise ValueError('Connection URLs cannot contain query strings or fragments')
    protocol = protocols[url.scheme.lower()]
    port = url.port if url.port is not None else (22 if protocol == 'SFTP' else 21)
    if not 1 <= port <= 65535:
        raise ValueError('Invalid port')
    username = unquote(url.username or '')
    path = unquote(url.path or '/')
    if any(ord(c) < 32 for c in username + path + url.hostname):
        raise ValueError('Control characters are not allowed')
    if not path.startswith('/'):
        raise ValueError('Remote path must be absolute')
    directory = path if path.endswith('/') else posixpath.dirname(path) or '/'
    filename = '' if path.endswith('/') else posixpath.basename(path)
    return {'protocol': protocol, 'host': url.hostname, 'port': port,
            'username': username, 'remote_path': directory, 'filename': filename}
