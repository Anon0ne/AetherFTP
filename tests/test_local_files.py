import logging
import os
from pathlib import Path
from unittest.mock import Mock
from local_files import read_directory


def test_unreadable_child_does_not_hide_readable_siblings(tmp_path, monkeypatch):
    (tmp_path/'good.txt').write_text('content'); (tmp_path/'broken').write_text('placeholder')
    original = Path.stat
    def stat(path, *args, **kwargs):
        if path.name == 'broken': raise FileNotFoundError('missing target')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'stat',stat)
    entries, skipped = read_directory(tmp_path)
    assert [entry[0] for entry in entries] == ['..','good.txt']
    assert skipped == 1


def test_failed_local_navigation_retains_previous_path_and_rows(tmp_path):
    os.environ['QT_QPA_PLATFORM']='offscreen'
    from PySide6.QtWidgets import QApplication
    from aetherftp import Session
    app=QApplication.instance() or QApplication([])
    session=Session(logging.getLogger('local-navigation'))
    try:
        (tmp_path/'good.txt').write_text('content')
        assert session.refresh_local(tmp_path)
        session.local_display.setText(str(tmp_path/'missing'))
        session.navigate('local')
        assert session.local_path == tmp_path
        assert session.local_display.text() == str(tmp_path)
        assert session.local_tree.topLevelItem(1).text(0) == 'good.txt'
        assert 'FileNotFoundError' in session.status.text()
    finally:
        session.timer.stop(); session.edit_timer.stop(); session.jobs.put(None); session.worker.join(1)
