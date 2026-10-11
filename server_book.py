"""AetherFTP server profiles. Passwords protected by Windows user DPAPI."""
import base64
import ctypes
import json
import os
import sys
from pathlib import Path

STORE = Path(os.environ.get('APPDATA', str(Path.home() / '.config'))) / 'AetherFTP' / 'servers.json'

if sys.platform == 'win32':
    from ctypes import wintypes
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_byte))]
    def _blob(data):
        buf = ctypes.create_string_buffer(data)
        return DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte))), buf
    def _crypt(data, decrypt=False):
        source, keep = _blob(data)
        output = DATA_BLOB()
        crypt32 = ctypes.windll.crypt32
        crypt32.CryptProtectData.argtypes = [ctypes.POINTER(DATA_BLOB), ctypes.c_wchar_p, ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB)]
        crypt32.CryptProtectData.restype = wintypes.BOOL
        crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB)]
        crypt32.CryptUnprotectData.restype = wintypes.BOOL
        if decrypt:
            ok = crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 0x1, ctypes.byref(output))
        else:
            ok = crypt32.CryptProtectData(ctypes.byref(source), 'AetherFTP credential', None, None, None, 0x1, ctypes.byref(output))
        if not ok:
            raise ctypes.WinError()
        try:
            return ctypes.string_at(output.pbData, output.cbData)
        finally:
            kernel32 = ctypes.windll.kernel32
            kernel32.LocalFree.argtypes = [ctypes.c_void_p]
            kernel32.LocalFree.restype = ctypes.c_void_p
            kernel32.LocalFree(ctypes.cast(output.pbData, ctypes.c_void_p))
else:
    def _crypt(data, decrypt=False):
        raise RuntimeError('Password saving requires Windows DPAPI; leave Save Password unchecked.')

def encrypt_password(password):
    return base64.b64encode(_crypt(password.encode('utf-8'))).decode('ascii')

def decrypt_password(value):
    return _crypt(base64.b64decode(value, validate=True), decrypt=True).decode('utf-8')

def load_profiles():
    if not STORE.exists():
        return []
    data = json.loads(STORE.read_text(encoding='utf-8'))
    if not isinstance(data, list):
        raise ValueError('Invalid Server Book format')
    return validate_profiles(data)

def save_profiles(profiles):
    profiles = validate_profiles(profiles)
    STORE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE.with_suffix('.tmp')
    try:
        with tmp.open('w', encoding='utf-8') as f:
            json.dump(profiles, f, indent=2)
        os.replace(tmp, STORE)
    finally:
        if tmp.exists():
            tmp.unlink()


def validate_profiles(profiles):
    if not isinstance(profiles, list):
        raise ValueError('Server Book must contain a list')
    names = set()
    allowed = {'id', 'name', 'host', 'port', 'username', 'protocol', 'password_dpapi', 'credential', 'local_path', 'remote_path'}
    for profile in profiles:
        if not isinstance(profile, dict) or set(profile) - allowed:
            raise ValueError('Unsupported profile fields; plaintext secrets are prohibited')
        for field in ('name', 'host', 'username', 'protocol'):
            if not isinstance(profile.get(field), str):
                raise ValueError('Invalid profile field: ' + field)
        if not profile['name'].strip() or not profile['host'].strip():
            raise ValueError('Profile name and host are required')
        name = profile['name'].casefold()
        if name in names:
            raise ValueError('Duplicate profile name')
        names.add(name)
        if profile['protocol'] not in ('FTP', 'FTPS', 'SFTP'):
            raise ValueError('Invalid protocol')
        if type(profile.get('port')) is not int or not 1 <= profile['port'] <= 65535:
            raise ValueError('Port must be 1–65535')
        for field in ('id', 'password_dpapi', 'local_path', 'remote_path'):
            if field in profile and not isinstance(profile[field], str):
                raise ValueError('Invalid field: ' + field)
        if profile.get('credential') not in (None, 'windows'):
            raise ValueError('Invalid credential mode')
        if profile.get('credential') and not profile.get('id'):
            raise ValueError('Credential profile requires an ID')
        if profile.get('credential') and profile.get('password_dpapi'):
            raise ValueError('Choose one credential storage mode')
    return profiles


def windows_vault():
    if sys.platform != 'win32':
        raise RuntimeError('Windows Credential Manager requires Windows')
    from keyring.backends.Windows import WinVaultKeyring
    return WinVaultKeyring()


def profile_password(profile):
    if profile.get('credential') == 'windows':
        return windows_vault().get_password('AetherFTP/' + profile['id'], 'password') or ''
    if profile.get('password_dpapi'):
        return decrypt_password(profile['password_dpapi'])
    return ''
