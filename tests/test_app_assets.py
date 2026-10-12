import os
from pathlib import Path
import struct
import sys
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
import app_assets


def test_application_icon_has_windows_sizes_and_loads():
    os.environ['QT_QPA_PLATFORM']='offscreen'
    app=QApplication.instance() or QApplication([])
    path=app_assets.icon_path()
    header=struct.unpack('<HHH',path.read_bytes()[:6])
    assert header == (0,1,7)
    icon=QIcon(str(path))
    assert not icon.isNull()
    assert {s.width() for s in icon.availableSizes()} == {16,24,32,48,64,128,256}
    assert not icon.pixmap(32,32).isNull()


def test_packaged_resource_path_uses_bundle(monkeypatch,tmp_path):
    monkeypatch.setattr(sys,'_MEIPASS',str(tmp_path),raising=False)
    assert app_assets.icon_path() == tmp_path/'assets'/'aetherftp.ico'
