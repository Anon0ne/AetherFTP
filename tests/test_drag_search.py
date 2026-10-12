import json
import logging
import os
import threading
import time
from pathlib import Path
from unittest.mock import Mock
import pytest
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import Qt,QMimeData,QPointF,QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication,QMessageBox,QInputDialog
from aetherftp import Session,FileTree
from file_tools import server_scope


@pytest.fixture
def session():
    app=QApplication.instance() or QApplication([])
    session=Session(logging.getLogger('drag-search'))
    session.connected=True;session.connection_args=('example.invalid',21,'test','secret','FTPES')
    yield session
    session.stop_operations();session.timer.stop();session.edit_timer.stop();session.queue_timer.stop()
    session.jobs.put(None);session.worker.join(2);session.transfer_pool.shutdown()


def remote_mime(session,entries):
    mime=QMimeData();mime.setData(FileTree.REMOTE_MIME,json.dumps({'session':session.drag_id,'scope':server_scope(session.connection_args),'entries':entries}).encode())
    return mime


def drop(tree,mime,point=QPointF(-1,-1)):
    event=QDropEvent(point,Qt.DropAction.CopyAction|Qt.DropAction.MoveAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
    tree.dropEvent(event)
    return event


def test_remote_to_local_drop_copies_and_same_remote_drop_moves(session,monkeypatch):
    monkeypatch.setattr(session,'download_entries',Mock());monkeypatch.setattr(session,'move_entries',Mock())
    entries=[['/files/a.txt',False]];mime=remote_mime(session,entries)
    event=drop(session.local_tree,mime)
    assert event.isAccepted() and event.dropAction()==Qt.DropAction.CopyAction
    session.download_entries.assert_called_once_with(entries,None)
    event=drop(session.remote_tree,mime)
    assert event.isAccepted() and event.dropAction()==Qt.DropAction.MoveAction
    session.move_entries.assert_called_once_with(entries,session.remote_path)


def test_cross_tab_remote_drop_rejected(session,monkeypatch):
    monkeypatch.setattr(session,'download_entries',Mock())
    mime=remote_mime(session,[['/files/a.txt',False]])
    payload=json.loads(bytes(mime.data(FileTree.REMOTE_MIME)));payload['session']='another-tab'
    mime.setData(FileTree.REMOTE_MIME,json.dumps(payload).encode())
    assert not drop(session.local_tree,mime).isAccepted()
    session.download_entries.assert_not_called()


def test_upload_drop_uses_hovered_folder(session,tmp_path,monkeypatch):
    monkeypatch.setattr(session,'upload_paths',Mock())
    tree=session.remote_tree;tree.resize(400,300);tree.show()
    session.fill(tree,[('destination',True,0,'/files/destination')]);QApplication.processEvents()
    mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(tmp_path/'a.txt'))])
    point=QPointF(tree.visualItemRect(tree.topLevelItem(0)).center())
    assert drop(tree,mime,point).isAccepted()
    session.upload_paths.assert_called_once_with([tmp_path/'a.txt'],'/files/destination')


def test_move_opens_destination_dialog(session,monkeypatch):
    dialog=Mock(return_value=('/target',True));monkeypatch.setattr(QInputDialog,'getText',dialog)
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(session,'submit',Mock())
    session.move_entries([('/files/a.txt',False)])
    dialog.assert_called_once();assert 'Destination remote folder' in dialog.call_args.args[2]
    assert session.submit.call_args.kwargs['operation']=='Move remote items'


def test_remote_management_blocks_active_operations_and_cancelled_delete(session,monkeypatch):
    monkeypatch.setattr(session,'submit',Mock())
    session.pending=1;session.move_entries([('/files/a.txt',False)],'/target');session.submit.assert_not_called();session.pending=0
    session.fill(session.remote_tree,[('a.txt',False,0,'/files/a.txt')]);session.remote_tree.topLevelItem(0).setSelected(True)
    monkeypatch.setattr(QMessageBox,'warning',lambda *args:QMessageBox.StandardButton.No)
    session.delete_selected();session.submit.assert_not_called()


def test_folder_download_queue_creates_empty_folders_and_finishes(session,tmp_path,monkeypatch):
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.Yes)
    tree={'/files':[('project',True,0)],'/files/project':[('empty',True,0),('a.txt',False,3)],'/files/project/empty':[]}
    session.client.listdir=Mock(side_effect=lambda path:tree[path])
    session.client.listdir_safe=session.client.listdir
    class Client:
        conn=None
        def connect(self,*args):self.conn=True
        def close(self):self.conn=None
        def download(self,source,dest,progress,resume):
            progress(0,3);Path(dest).write_bytes(b'abc');progress(3,3)
    session.transfer_pool.factory=Client
    session.download_entries([('/files/project',True)],tmp_path)
    deadline=time.monotonic()+3
    while session.pending and time.monotonic()<deadline:
        QApplication.processEvents();session.pump();time.sleep(.005)
    assert session.pending==0
    assert (tmp_path/'project'/'empty').is_dir()
    assert (tmp_path/'project'/'a.txt').read_bytes()==b'abc'


def test_modeless_search_results_and_stop(session,monkeypatch):
    session.client.listdir=Mock(return_value=[('a.txt',False,3),('b.zip',False,4)])
    session.open_search();dialog=session.search_dialog;dialog.pattern.setText('*.txt');dialog.begin()
    deadline=time.monotonic()+2
    while (session.pending or dialog.busy) and time.monotonic()<deadline:QApplication.processEvents();session.pump();time.sleep(.005)
    assert not dialog.busy and dialog.results.topLevelItemCount()==1
    assert dialog.results.topLevelItem(0).text(1)=='/a.txt'
    dialog.begin();dialog.stop.click();assert dialog.cancelled.is_set()
    deadline=time.monotonic()+2
    while session.pending and time.monotonic()<deadline:session.pump();time.sleep(.005)
    assert not dialog.busy;dialog.close()

def test_mutation_lock_blocks_new_downloads(session,monkeypatch):
    session.managing_remote=True
    monkeypatch.setattr(session,'submit',Mock())
    session.download_entries([('/files/a.txt',False)])
    session.submit.assert_not_called()
    session.managing_remote=False


def test_stopping_paused_folder_download_releases_batch_holds(session,tmp_path,monkeypatch):
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.Yes)
    session.client.listdir_safe=Mock(return_value=[('a.txt',False,3)])
    session.client.check_directory_traversal=Mock()
    session.transfer_pool.set_paused(True)
    session.download_entries([('/files/project',True)],tmp_path)
    deadline=time.monotonic()+2
    while not session.active_batches and time.monotonic()<deadline:session.pump();time.sleep(.005)
    assert session.active_batches
    session.queue_timer.stop();session.dispatch_upload_batch();session.stop_operations()
    deadline=time.monotonic()+2
    while session.pending and time.monotonic()<deadline:session.pump();time.sleep(.005)
    assert session.pending==0 and not session.active_batches
    assert not (tmp_path/'project'/'a.txt').exists()
