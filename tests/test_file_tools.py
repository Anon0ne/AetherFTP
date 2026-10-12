import hashlib
import json
import logging
import os
import time
from pathlib import Path
from unittest.mock import Mock
import pytest
import file_tools as tools


def test_bookmarks_are_scoped_and_contain_no_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, 'BOOKMARKS', tmp_path/'bookmarks.json')
    args = ('example.invalid',21,'test','secret','FTPES')
    scope = tools.server_scope(args)
    assert scope == tools.server_scope(args[:3]+('new-secret',args[4]))
    assert scope != tools.server_scope(('other.invalid',)+args[1:])
    records = [dict(name='Project',scope=scope,local=str(tmp_path),remote='/files')]
    tools.save_bookmarks(records)
    assert tools.load_bookmarks() == records
    text = tools.BOOKMARKS.read_text()
    assert 'secret' not in text and 'example.invalid' not in text
    with pytest.raises(ValueError): tools.save_bookmarks([records[0]|{'password':'secret'}])


def test_paired_paths_map_both_directions_and_reject_escape(tmp_path):
    root = tmp_path/'project'; (root/'nested').mkdir(parents=True)
    assert tools.paired_paths(root,'/files','local',root/'nested') == (root/'nested','/files/nested')
    assert tools.paired_paths(root,'/files','remote','/files/nested') == (root/'nested','/files/nested')
    for side, target in [('local',tmp_path),('remote','/other'),('remote','/files/../../etc'),('remote','/files/C:evil')]:
        with pytest.raises(ValueError): tools.paired_paths(root,'/files',side,target)


class MemoryClient:
    def __init__(self): self.data=b'original'; self.uploads=[]
    def download(self, remote, local, callback, resume=False):
        assert resume is False
        Path(local).write_bytes(self.data); callback(0,len(self.data)); callback(len(self.data),len(self.data))
    def upload(self, local, remote, callback, resume=False):
        assert resume is False
        self.data=Path(local).read_bytes(); self.uploads.append((remote,self.data))
        callback(0,len(self.data)); callback(len(self.data),len(self.data))


def test_remote_edit_conflict_prevents_overwrite_and_preserves_local_changes(tmp_path):
    client=MemoryClient(); edit=tools.RemoteEdit('/files/config.txt',tmp_path)
    try:
        edit.download(client); edit.path.write_bytes(b'local change'); client.data=b'other user change'
        with pytest.raises(RuntimeError,match='Remote file changed'): edit.upload_changes(client)
        assert client.uploads == [] and client.data == b'other user change'
        assert edit.path.read_bytes() == b'local change'
    finally: edit.close()


def test_remote_edit_uses_snapshot_and_tracks_uploaded_content(tmp_path):
    client=MemoryClient(); edit=tools.RemoteEdit('/files/.upload-snapshot',tmp_path)
    try:
        edit.download(client)
        assert edit.upload_changes(client) is False and client.uploads == []
        edit.path.write_bytes(b'first save')
        original_upload=client.upload
        def upload(*args,**kwargs):
            edit.path.write_bytes(b'second save during upload'); original_upload(*args,**kwargs)
        client.upload=upload
        assert edit.upload_changes(client) is True
        assert client.data == b'first save'
        assert edit.original_hash == hashlib.sha256(b'first save').hexdigest()
        assert edit.path.read_bytes() == b'second save during upload'
    finally: edit.close()
    assert not edit.path.parent.exists()


@pytest.mark.parametrize('name',['..','bad:name','bad\\name','bad?.txt','.aether-work'])
def test_remote_edit_rejects_unsafe_names(tmp_path,name):
    with pytest.raises(ValueError): tools.RemoteEdit('/files/'+name,tmp_path)


@pytest.mark.parametrize('failure',[False,True])
def test_synchronized_navigation_updates_pair_only_after_success(tmp_path,failure):
    os.environ['QT_QPA_PLATFORM']='offscreen'
    from PySide6.QtWidgets import QApplication
    from aetherftp import Session
    app=QApplication.instance() or QApplication([])
    session=Session(logging.getLogger('paired-navigation'))
    root=tmp_path/'root'; (root/'nested').mkdir(parents=True)
    session.local_path=root; session.remote_path='/files'; session.connected=True
    session.sync_roots=(root,'/files'); session.client.listdir=Mock(side_effect=RuntimeError('Unavailable') if failure else None,return_value=[])
    try:
        session.local_display.setText(str(root/'nested')); session.navigate('local')
        assert session.local_path == root
        deadline=time.monotonic()+2
        while session.pending and time.monotonic()<deadline: session.pump(); time.sleep(.01)
        assert session.pending == 0
        assert session.local_path == (root if failure else root/'nested')
        assert session.remote_path == ('/files' if failure else '/files/nested')
    finally:
        session.timer.stop(); session.edit_timer.stop(); session.jobs.put(None); session.worker.join(1)


def test_editing_sessions_block_reconnect_and_disconnect():
    os.environ['QT_QPA_PLATFORM']='offscreen'
    from PySide6.QtWidgets import QApplication
    from aetherftp import Session
    app=QApplication.instance() or QApplication([])
    session=Session(logging.getLogger('edit-connection-guard'))
    session.edits=[object()]; session.connected=True
    try:
        session.connect_server(); assert 'Stop remote editing' in session.status.text()
        session.disconnect(); assert session.connected
        assert session.pending == 0
    finally:
        session.edits=[]; session.timer.stop(); session.edit_timer.stop(); session.jobs.put(None); session.worker.join(1)

def test_edit_download_and_upload_use_queue_without_resuming(tmp_path,monkeypatch):
    os.environ['QT_QPA_PLATFORM']='offscreen'
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    import aetherftp
    from aetherftp import Session
    app=QApplication.instance() or QApplication([])
    session=Session(logging.getLogger('editing-queue'))
    class QueueClient(MemoryClient):
        def __init__(self): super().__init__(); self.conn=None
        def connect(self,*args): self.conn=object()
        def close(self): self.conn=None
    client=QueueClient()
    session.transfer_pool.factory=lambda:client
    session.connected=True; session.connection_args=('example.invalid',21,'test','secret','FTPES')
    monkeypatch.setattr(aetherftp,'STORE',tmp_path/'servers.json')
    opened=[]; monkeypatch.setattr(session,'open_editor',opened.append)
    monkeypatch.setattr(session,'refresh_remote',lambda:None)
    session.fill(session.remote_tree,[('config.txt',False,8,'/files/config.txt')])
    session.remote_tree.topLevelItem(0).setSelected(True)
    session.resume.setChecked(True)
    def drain():
        deadline=time.monotonic()+3
        while session.pending and time.monotonic()<deadline:
            session.pump(); app.processEvents(); time.sleep(.01)
        assert session.pending == 0
    try:
        session.edit_remote_file(); session.edit_remote_file()
        drain()
        assert len(session.edits)==1 and len(opened)==1
        edit=session.edits[0]; assert edit.path.read_bytes()==b'original'
        assert not session.pending_edits
        edit.path.write_bytes(b'edited')
        session.upload_edit(edit); drain()
        assert client.data==b'edited'
        assert session.transfers.topLevelItemCount()==1
        assert 'Completed' in session.progress_bars[0].format()
    finally:
        for edit in session.edits: edit.close()
        session.edits=[]; session.timer.stop(); session.edit_timer.stop(); session.jobs.put(None); session.worker.join(1)

def test_editor_save_requires_confirmation_and_keeps_copy_on_decline(tmp_path,monkeypatch):
    os.environ['QT_QPA_PLATFORM']='offscreen'
    from PySide6.QtWidgets import QApplication,QMessageBox
    from aetherftp import Session
    app=QApplication.instance() or QApplication([])
    session=Session(logging.getLogger('editor-confirmation')); session.connected=True
    edit=tools.RemoteEdit('/files/config.txt',tmp_path); edit.download(MemoryClient()); session.edits=[edit]
    calls=[]; monkeypatch.setattr(session,'upload_edit',calls.append)
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.No)
    try:
        edit.path.write_bytes(b'first change'); session.check_edit_changes()
        assert calls==[] and edit.path.exists()
        session.check_edit_changes(); assert calls==[]
        monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.Yes)
        edit.path.write_bytes(b'second change'); session.check_edit_changes()
        assert calls==[edit] and not session.edit_prompt_active
    finally:
        edit.close(); session.edits=[]; session.timer.stop(); session.edit_timer.stop(); session.jobs.put(None); session.worker.join(1)

def test_new_remote_file_refuses_existing_ftp_file():
    client=MemoryClient(); client.kind='FTPES'; client.listdir=Mock(return_value=[('existing.txt',False,8)])
    with pytest.raises(FileExistsError): tools.create_remote_file(client,'unused','/files/existing.txt',Mock())
    assert client.uploads == []


def test_new_sftp_file_uses_exclusive_creation():
    from unittest.mock import MagicMock
    client=Mock(); client.kind='SFTP'; client.conn.open=MagicMock()
    progress=Mock()
    tools.create_remote_file(client,'unused','/files/new.txt',progress)
    client.conn.open.assert_called_once_with('/files/new.txt','wx')
    client.upload.assert_not_called(); progress.assert_called_once_with(0,0)


@pytest.mark.parametrize('name',['../escape','bad/name','bad\\name','..','CON','bad?.txt','bad\nname'])
def test_new_remote_name_validation(name):
    with pytest.raises(ValueError): tools.validate_remote_name(name)

@pytest.mark.parametrize('directory',[False,True])
def test_remote_right_click_offers_creation_and_file_editing(monkeypatch,directory):
    os.environ['QT_QPA_PLATFORM']='offscreen'
    from PySide6.QtWidgets import QApplication,QMenu
    from PySide6.QtCore import QPoint,QTimer
    from aetherftp import Session
    app=QApplication.instance() or QApplication([])
    session=Session(logging.getLogger('remote-context')); session.connected=True
    session.fill(session.remote_tree,[('item',directory,0,'/item')])
    session.remote_tree.topLevelItem(0).setSelected(True)
    actions=[]
    def inspect_and_close():
        for menu in QApplication.topLevelWidgets():
            if isinstance(menu,QMenu) and menu.isVisible():
                actions.extend((a.text(),a.isEnabled()) for a in menu.actions() if a.text())
                menu.close()
    QTimer.singleShot(0,inspect_and_close)
    QTimer.singleShot(1000,inspect_and_close)
    try:
        session.remote_context_menu(QPoint(0,0))
        assert ('Edit in Notepad',not directory) in actions
        assert ('New file…',True) in actions and ('New folder…',True) in actions
    finally:
        session.timer.stop();session.edit_timer.stop();session.jobs.put(None);session.worker.join(1)
