import io
import logging
import os
import threading
import time
from pathlib import Path
from unittest.mock import Mock
import pytest
from transfer_control import OperationCancelled
from transfer_pool import BandwidthLimiter,TransferPool
from user_settings import DEFAULTS


def test_bandwidth_wait_can_be_cancelled_promptly():
    limiter=BandwidthLimiter(.000001); cancelled=threading.Event(); done=threading.Event()
    def checkpoint():
        if cancelled.is_set(): raise OperationCancelled()
    def run():
        try: limiter.consume(65536,checkpoint)
        except OperationCancelled: done.set()
    thread=threading.Thread(target=run);thread.start();time.sleep(.03);cancelled.set()
    assert done.wait(.5);thread.join(1)


def test_paused_pool_waits_for_resume_and_cancel_drains_blocked_barrier():
    class FakeClient:
        conn=None
        def close(self): self.conn=None
    completed=threading.Event();cancelled=threading.Event();results=[]
    def run(client,ensure,job):
        try: pool.checkpoint(cancelled);results.append('ran')
        except OperationCancelled: results.append('cancelled')
        completed.set()
    pool=TransferPool(FakeClient,run);pool.set_paused(True)
    try:
        pool.submit('Upload','target',(),None,barrier=threading.Event(),cancelled=cancelled)
        assert not completed.wait(.05)
        pool.cancel(cancelled)
        assert completed.wait(1) and results==['cancelled']
    finally:pool.set_paused(False);pool.shutdown()


def test_paused_checkpoint_resumes_without_cancelling():
    class FakeClient:
        conn=None
        def close(self): pass
    pool=TransferPool(FakeClient,lambda *_:None);pool.set_paused(True)
    done=threading.Event();thread=threading.Thread(target=lambda:(pool.checkpoint(threading.Event()),done.set()))
    thread.start()
    try:
        assert not done.wait(.05)
        pool.set_paused(False);assert done.wait(1)
    finally:pool.set_paused(False);thread.join(1);pool.shutdown()


@pytest.mark.parametrize('partial_dispatch',[False,True])
def test_stop_folder_queue_releases_holds_and_pending_counts(monkeypatch,partial_dispatch):
    os.environ['QT_QPA_PLATFORM']='offscreen'
    from PySide6.QtWidgets import QApplication,QMessageBox
    import aetherftp
    app=QApplication.instance() or QApplication([])
    session=aetherftp.Session(logging.getLogger('cancel-folders'))
    session.connected=True;session.connection_args=('example.invalid',21,'test','secret','FTPES')
    session.transfer_pool.set_paused(True)
    files=[('local'+str(i),'/files/'+str(i)) for i in range(100 if partial_dispatch else 5)]
    monkeypatch.setattr(aetherftp,'plan_uploads',lambda *args:([],files,0))
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(session,'refresh_remote',Mock())
    class FakeClient:
        conn=None
        def close(self): self.conn=None
        def connect(self,*args): raise AssertionError('Cancelled files must not connect')
    session.transfer_pool.factory=FakeClient
    try:
        session.upload_paths([Path('source')])
        deadline=time.monotonic()+2
        while not session.active_batches and time.monotonic()<deadline:session.pump();time.sleep(.01)
        assert session.active_batches
        session.queue_timer.stop();session.dispatch_upload_batch()
        session.stop_operations()
        deadline=time.monotonic()+2
        while session.pending and time.monotonic()<deadline:session.pump();time.sleep(.01)
        assert session.pending==0 and not session.active_batches and not session.upload_batches
        assert not session.connected
        session.refresh_remote.assert_not_called()
        assert all(session.transfers.topLevelItem(i).data(1, aetherftp.Qt.ItemDataRole.UserRole)=='Cancelled' for i in range(session.transfers.topLevelItemCount()))
    finally:
        session.timer.stop();session.edit_timer.stop();session.queue_timer.stop();session.jobs.put(None);session.worker.join(1)


def test_close_offers_stop_and_exits_when_jobs_finish(monkeypatch):
    os.environ['QT_QPA_PLATFORM']='offscreen'
    from PySide6.QtWidgets import QApplication,QMessageBox
    from aetherftp import App
    app=QApplication.instance() or QApplication([])
    window=App(logging.getLogger('stop-exit'));session=window.tabs.widget(0)
    started=threading.Event();release=threading.Event()
    session.client.cancel=release.set
    session.submit(lambda:(started.set(),release.wait(2)),operation='Test operation')
    assert started.wait(1)
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.Yes)
    window.show();window.close()
    deadline=time.monotonic()+2
    while window.tabs.count() and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
    assert window.tabs.count()==0 and not window.isVisible()


def test_client_cancel_interrupts_control_and_data_sockets():
    import socket
    from types import SimpleNamespace
    from transfer_client import Client
    control,control_peer=socket.socketpair();data,data_peer=socket.socketpair()
    client=Client();client.conn=SimpleNamespace(sock=control,active_data=data)
    try:
        client.cancel()
        control_peer.settimeout(1);data_peer.settimeout(1)
        assert control_peer.recv(1)==b'' and data_peer.recv(1)==b''
    finally:
        control.close();control_peer.close();data.close();data_peer.close()
