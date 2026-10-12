"""Source and packaged application artwork and Windows taskbar identity."""
from pathlib import Path
import sys


def icon_path():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)) / 'assets' / 'aetherftp.ico'


def set_windows_identity():
    if sys.platform != 'win32': return
    import ctypes
    setter = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
    setter.argtypes = [ctypes.c_wchar_p]
    setter.restype = ctypes.c_long
    if setter('Anon0ne.AetherFTP') != 0:
        raise OSError('Windows application identity could not be set')
