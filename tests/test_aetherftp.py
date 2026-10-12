import io
import json
import logging
import os
from pathlib import Path
from unittest.mock import Mock, call
import pytest
import server_book as book
from transfer_client import Client


def profile():
    return dict(name='Test', host='example.invalid', port=22, username='test', protocol='SFTP')


def test_profile_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(book, 'STORE', tmp_path / 'servers.json')
    book.save_profiles([profile()])
    assert book.load_profiles() == [profile()]
    assert not book.STORE.with_suffix('.tmp').exists()


@pytest.mark.parametrize('change', [{'password':'secret'}, {'port':True}, {'protocol':'bad'}, {'name':''}, {'host':None}])
def test_reject_bad_profile(change):
    p = profile(); p.update(change)
    with pytest.raises(ValueError): book.validate_profiles([p])


def test_duplicates():
    with pytest.raises(ValueError): book.validate_profiles([profile(), profile()])


def test_dpapi_roundtrip():
    if os.name != 'nt': pytest.skip('Windows only')
    encrypted = book.encrypt_password('temporary-test-secret')
    assert 'temporary-test-secret' not in encrypted
    assert book.decrypt_password(encrypted) == 'temporary-test-secret'


def test_credential_lookup(monkeypatch):
    vault = Mock(); vault.get_password.return_value = 'test-secret'
    monkeypatch.setattr(book, 'windows_vault', lambda: vault)
    assert book.profile_password({'id':'test', 'credential':'windows'}) == 'test-secret'
    vault.get_password.assert_called_once_with('AetherFTP/test', 'password')


def test_ftp_resume_download(tmp_path):
    c = Client(); c.kind = 'FTP'; c.conn = Mock(); c.conn.size.return_value = 6
    local = tmp_path / 'file'; local.write_bytes(b'abc')
    def retrieve(command, callback, rest):
        assert rest == 3; callback(b'def')
    c.conn.retrbinary.side_effect = retrieve
    progress = Mock(); c.download('/file', str(local), progress, resume=True)
    assert local.read_bytes() == b'abcdef'; progress.assert_called_with(6, 6)


def test_ftp_resume_upload(tmp_path):
    c = Client(); c.kind = 'FTP'; c.conn = Mock(); c.conn.size.return_value = 3
    local = tmp_path / 'file'; local.write_bytes(b'abcdef')
    def store(command, stream, callback, rest):
        assert rest == 3; assert stream.read() == b'def'; callback(b'def')
    c.conn.storbinary.side_effect = store
    progress = Mock(); c.upload(str(local), '/file', progress, resume=True)
    progress.assert_called_with(6, 6)


def test_oversized_resume_preserves_file(tmp_path):
    c = Client(); c.kind = 'FTP'; c.conn = Mock(); c.conn.size.return_value = 1
    local = tmp_path / 'file'; local.write_bytes(b'abc')
    with pytest.raises(ValueError): c.download('/file', str(local), Mock(), resume=True)
    assert local.read_bytes() == b'abc'


def test_ftps_verifies_certificates(monkeypatch):
    import transfer_client
    ftp = Mock(); factory = Mock(return_value=ftp)
    monkeypatch.setattr(transfer_client, 'ReuseFTP_TLS', factory)
    Client().connect('example.invalid',21,'test','test','FTPS')
    context = factory.call_args.kwargs['context']
    assert context.check_hostname
    ftp.prot_p.assert_called_once()


def test_gui_tabs_and_serial_queue(monkeypatch):
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from PySide6.QtWidgets import QApplication
    from aetherftp import App
    app = QApplication.instance() or QApplication([])
    window = App(logging.getLogger('test')); window.add_tab()
    assert window.tabs.count() == 2
    session = window.tabs.widget(0)
    result = []
    session.submit(lambda: result.append(1))
    session.submit(lambda: result.append(2))
    import time
    deadline = time.monotonic() + 3
    while session.pending and time.monotonic() < deadline:
        app.processEvents(); time.sleep(.01)
    assert result == [1,2]; assert session.pending == 0
    window.close(); app.processEvents()


def test_failed_login_closes_socket(monkeypatch):
    import transfer_client
    ftp = Mock(); ftp.login.side_effect = RuntimeError('private response')
    monkeypatch.setattr(transfer_client.ftplib, 'FTP', lambda: ftp)
    client = Client()
    with pytest.raises(RuntimeError): client.connect('example.invalid',21,'test','secret','FTP')
    ftp.close.assert_called_once(); assert client.conn is None


def test_sftp_resume_download(tmp_path):
    c = Client(); c.kind = 'SFTP'; c.conn = Mock()
    c.conn.stat.return_value.st_size = 6
    stream = io.BytesIO(b'abcdef'); c.conn.open.return_value = stream
    dest = tmp_path / 'file'; dest.write_bytes(b'abc')
    progress = Mock(); c.download('/file', str(dest), progress, resume=True)
    assert dest.read_bytes() == b'abcdef'; progress.assert_called_with(6,6)


def test_error_logs_do_not_contain_server_response(tmp_path, monkeypatch):
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from PySide6.QtWidgets import QApplication
    from aetherftp import Session
    app = QApplication.instance() or QApplication([])
    output = io.StringIO(); logger = logging.getLogger('privacy-test')
    logger.addHandler(logging.StreamHandler(output)); logger.setLevel(logging.INFO)
    session = Session(logger)
    session.connection_secrets = ('secret-password', 'private-host')
    def fail(): raise RuntimeError('secret-password private-host')
    session.submit(fail)
    import time
    deadline = time.monotonic() + 3
    while session.pending and time.monotonic() < deadline:
        session.pump(); time.sleep(.01)
    assert 'RuntimeError' in output.getvalue()
    assert 'secret-password' not in output.getvalue(); assert 'private-host' not in output.getvalue()
    session.timer.stop(); session.jobs.put(None); session.worker.join(1)


def test_transfer_stats_excludes_resumed_bytes():
    from transfer_stats import TransferStats
    clock = Mock(return_value=0.0)
    stats = TransferStats(clock)
    stats.update(2_000_000, 4_000_000)
    clock.return_value = 1.0
    percent, rate = stats.update(3_000_000, 4_000_000)
    assert percent == 75 and rate == 1.0
    clock.return_value = 2.0
    stats.update(4_000_000, 4_000_000)
    summary = stats.summary()
    assert summary['bytes_transferred'] == 2_000_000
    assert summary['average_mbps'] == 1.0
    assert summary['duration_seconds'] == 2.0


def test_unknown_and_empty_transfer_sizes():
    from transfer_stats import TransferStats
    stats = TransferStats(lambda: 0)
    assert stats.update(0, 0) == (None, 0)
    assert stats.summary()['average_mbps'] == 0


@pytest.mark.parametrize('failure', [False, True])
def test_transfer_bars_and_timing_events(failure, monkeypatch):
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from PySide6.QtWidgets import QApplication
    from aetherftp import Session, STYLE
    import threading
    import time
    app = QApplication.instance() or QApplication([]); app.setStyleSheet(STYLE)
    output = io.StringIO(); logger = logging.getLogger('transfer-test-' + str(failure))
    handler = logging.StreamHandler(output); logger.addHandler(handler); logger.setLevel(logging.INFO)
    session = Session(logger); session.connected = True
    session.connection_secrets = ('secret', 'private host')
    monkeypatch.setattr(session, 'refresh_remote', lambda: None)
    ready = threading.Event(); release = threading.Event()
    def upload(source, dest, callback, resume):
        callback(0, 1_000_000)
        time.sleep(.21)
        callback(500_000, 1_000_000); ready.set()
        if not release.wait(3): raise TimeoutError()
        if failure: raise RuntimeError('private host secret')
        callback(1_000_000, 1_000_000)
    monkeypatch.setattr(session.client, 'upload', upload)
    try:
        session.enqueue_transfer('Upload', '/private/file.txt', '/private/remote.txt')
        assert ready.wait(3)
        session.pump(); app.processEvents()
        bar = session.progress_bars[0]
        assert bar.value() == 50 and '50%' in bar.format() and 'MB/s' in bar.format()
        assert session.activity_toggle.isChecked()
        release.set()
        deadline = time.monotonic() + 3
        while session.pending and time.monotonic() < deadline:
            session.pump(); app.processEvents(); time.sleep(.01)
        assert session.pending == 0
        assert ('Failed' if failure else 'Completed') in bar.format()
        if not failure: assert bar.value() == 100
        records = [json.loads(line) for line in output.getvalue().splitlines()]
        transfer_records = [r for r in records if r['event'].startswith('transfer_')]
        assert [r['event'] for r in transfer_records] == ['transfer_started', 'transfer_failed' if failure else 'transfer_completed']
        finished = transfer_records[-1]
        assert finished['duration_seconds'] >= .2
        assert finished['bytes_transferred'] == (500_000 if failure else 1_000_000)
        assert finished['average_mbps'] > 0
        assert 'timestamp' in finished
        assert '/private' not in output.getvalue() and 'secret' not in output.getvalue()
        assert 'Upload' in session.log.toPlainText()
    finally:
        release.set(); session.worker.join(.1)
        session.timer.stop(); session.jobs.put(None); session.worker.join(3)
        logger.removeHandler(handler)


def test_ftpes_url_custom_port_and_file():
    from connection_url import parse_connection_url
    result = parse_connection_url('ftpes://sampleuser@example.invalid:2990/files/sample.txt')
    assert result == dict(protocol='FTPES', host='example.invalid', port=2990, username='sampleuser', remote_path='/files', filename='sample.txt')


@pytest.mark.parametrize('url', ['ftpes://user:secret@example.invalid/', 'ftpes://example.invalid:0/', 'ftpes://example.invalid:65536/', 'https://example.invalid/', 'ftpes://example.invalid/%0d%0aDELE', 'ftpes://example.invalid/?token=secret'])
def test_reject_unsafe_connection_urls(url):
    from connection_url import parse_connection_url
    with pytest.raises(ValueError): parse_connection_url(url)


def test_ftpes_url_defaults_and_ipv6():
    from connection_url import parse_connection_url
    result = parse_connection_url('ftpes://sample%20user@[::1]/files/')
    assert result['host'] == '::1' and result['port'] == 21
    assert result['username'] == 'sample user' and result['remote_path'] == '/files/'
    assert result['filename'] == ''


def test_ftpes_authenticates_tls_before_login(monkeypatch):
    import transfer_client
    ftp = Mock(); factory = Mock(return_value=ftp)
    monkeypatch.setattr(transfer_client, 'ReuseFTP_TLS', factory)
    client = Client(); client.connect('example.invalid',2990,'sampleuser','secret','FTPES')
    assert [c[0] for c in ftp.mock_calls] == ['connect','auth','sock.version','login','prot_p','voidcmd']
    ftp.connect.assert_called_once_with('example.invalid',2990,timeout=20)
    assert factory.call_args.kwargs['context'].check_hostname
    assert client.kind == 'FTPES'
    p = profile(); p['protocol'] = 'FTPES'; assert book.validate_profiles([p]) == [p]


def test_ftpes_tls_failure_never_sends_credentials(monkeypatch):
    import ssl
    import transfer_client
    ftp = Mock(); ftp.auth.side_effect = ssl.SSLCertVerificationError('untrusted certificate')
    monkeypatch.setattr(transfer_client, 'ReuseFTP_TLS', Mock(return_value=ftp))
    with pytest.raises(ssl.SSLCertVerificationError): Client().connect('example.invalid',2990,'sampleuser','secret','FTPES')
    ftp.login.assert_not_called(); ftp.close.assert_called_once()


def test_gui_connection_url_load_and_file_selection(monkeypatch):
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from PySide6.QtWidgets import QApplication
    from aetherftp import Session
    import time
    app = QApplication.instance() or QApplication([])
    session = Session(logging.getLogger('url-test'))
    try:
        session.password.setText('old-secret')
        session.host.setText('ftpes://sampleuser@example.invalid:2990/files/sample.txt')
        assert session.load_connection_url()
        assert session.protocol.currentText() == 'FTPES'
        assert session.port.text() == '2990' and session.remote_display.text() == '/files'
        assert session.password.text() == ''
        session.password.setText('new-secret')
        connect = Mock(); monkeypatch.setattr(session.client,'connect',connect)
        monkeypatch.setattr(session.client,'listdir',Mock(return_value=[('sample.txt',False,100)]))
        session.connect_server()
        deadline = time.monotonic() + 3
        while session.pending and time.monotonic() < deadline:
            session.pump(); app.processEvents(); time.sleep(.01)
        connect.assert_called_once_with('example.invalid',2990,'sampleuser','new-secret','FTPES')
        assert session.remote_tree.selectedItems()[0].text(0) == 'sample.txt'
    finally:
        session.timer.stop(); session.jobs.put(None); session.worker.join(3)


def test_tls_data_socket_reuses_control_session(monkeypatch):
    import transfer_client
    control = Mock(); data = Mock(); protected = Mock(); context = Mock()
    context.wrap_socket.return_value = protected
    ftp = transfer_client.ReuseFTP_TLS(context=context)
    ftp.host = 'example.invalid'; ftp.sock = control; ftp._prot_p = True
    base = Mock(return_value=(data,123)); monkeypatch.setattr(transfer_client.ftplib.FTP,'ntransfercmd',base)
    assert ftp.ntransfercmd('RETR sample.txt',42) == (protected,123)
    base.assert_called_once_with(ftp,'RETR sample.txt',42)
    context.wrap_socket.assert_called_once_with(data,server_hostname='example.invalid',session=control.session)


def test_failed_data_tls_closes_socket(monkeypatch):
    import ssl
    import transfer_client
    data = Mock(); context = Mock(); context.wrap_socket.side_effect = ssl.SSLError('handshake failed')
    ftp = transfer_client.ReuseFTP_TLS(context=context); ftp.host='example.invalid'; ftp.sock=Mock(); ftp._prot_p=True
    monkeypatch.setattr(transfer_client.ftplib.FTP,'ntransfercmd',Mock(return_value=(data,None)))
    with pytest.raises(ssl.SSLError): ftp.ntransfercmd('MLSD')
    data.close.assert_called_once()


def test_unprotected_data_does_not_wrap(monkeypatch):
    import transfer_client
    data=Mock(); context=Mock(); ftp=transfer_client.ReuseFTP_TLS(context=context)
    monkeypatch.setattr(transfer_client.ftplib.FTP,'ntransfercmd',Mock(return_value=(data,None)))
    assert ftp.ntransfercmd('NLST') == (data,None)
    context.wrap_socket.assert_not_called()


def test_server_errors_are_logged_with_credentials_redacted(monkeypatch):
    import ftplib
    import time
    from PySide6.QtWidgets import QApplication
    from aetherftp import Session
    os.environ['QT_QPA_PLATFORM']='offscreen'
    app=QApplication.instance() or QApplication([])
    output=io.StringIO(); logger=logging.getLogger('server-error-test')
    handler=logging.StreamHandler(output); logger.addHandler(handler); logger.setLevel(logging.INFO)
    session=Session(logger)
    session.host.setText('example.invalid'); session.user.setText('private-user'); session.password.setText('private-password')
    def fail(*args):
        session.client.step('Authenticating user')
        raise ftplib.error_perm('530 Login incorrect for private-user on example.invalid; password=private-password')
    monkeypatch.setattr(session.client,'connect',fail)
    try:
        session.connect_server()
        deadline=time.monotonic()+3
        while session.pending and time.monotonic()<deadline:
            session.pump(); app.processEvents(); time.sleep(.01)
        visible=session.log.toPlainText(); persisted=output.getvalue()
        assert '530 Login incorrect' in visible and '530 Login incorrect' in persisted
        assert 'Authenticating user' in visible
        for secret in ('private-user','private-password','example.invalid'):
            assert secret not in visible and secret not in persisted
        assert session.activity.currentIndex()==1
    finally:
        session.timer.stop(); session.jobs.put(None); session.worker.join(3); logger.removeHandler(handler)


def test_folder_plan_preserves_nested_and_empty_directories(tmp_path):
    from upload_plan import plan_uploads
    source=tmp_path/'project'; (source/'nested').mkdir(parents=True); (source/'empty').mkdir()
    (source/'top.txt').write_text('top'); (source/'nested'/'child.txt').write_text('child')
    directories, files, skipped=plan_uploads([source],'/files')
    assert directories == ['/files/project','/files/project/empty','/files/project/nested']
    assert dict(files) == {str(source/'top.txt'):'/files/project/top.txt',str(source/'nested'/'child.txt'):'/files/project/nested/child.txt'}
    assert skipped==0


def test_folder_plan_skips_links(tmp_path, monkeypatch):
    import upload_plan
    source=tmp_path/'project'; source.mkdir(); (source/'link').mkdir(); (source/'link'/'outside.txt').write_text('not uploaded')
    monkeypatch.setattr(upload_plan,'is_link',lambda p: p.name=='link')
    dirs, files, skipped=upload_plan.plan_uploads([source],'/files')
    assert dirs==['/files/project'] and files==[] and skipped==1


def test_existing_ftp_directory_and_permission_failure():
    import ftplib
    c=Client(); c.kind='FTPES'; c.conn=Mock(); c.conn.mkd.side_effect=ftplib.error_perm('550 Exists or denied'); c.conn.pwd.return_value='/original'
    c.ensure_directory('/files/project')
    assert c.conn.cwd.call_args_list == [call('/files/project'),call('/original')]
    c.conn.cwd.side_effect=lambda path: (_ for _ in ()).throw(ftplib.error_perm('550 Denied')) if path=='/files/denied' else None
    with pytest.raises(ftplib.error_perm): c.ensure_directory('/files/denied')


def test_existing_sftp_directory_is_verified():
    import stat
    c=Client(); c.kind='SFTP'; c.conn=Mock(); c.conn.mkdir.side_effect=OSError('Exists')
    c.conn.stat.return_value.st_mode=stat.S_IFDIR
    c.ensure_directory('/files/project')
    c.conn.stat.return_value.st_mode=stat.S_IFREG
    with pytest.raises(OSError): c.ensure_directory('/files/project')


def test_gui_queues_folder_creation_before_files(tmp_path,monkeypatch):
    import time
    from PySide6.QtWidgets import QApplication,QMessageBox
    from aetherftp import Session
    os.environ['QT_QPA_PLATFORM']='offscreen'; app=QApplication.instance() or QApplication([])
    source=tmp_path/'project'; (source/'empty').mkdir(parents=True); (source/'child.txt').write_bytes(b'data')
    session=Session(logging.getLogger('folder-test')); session.connected=True; session.remote_path='/files'
    calls=[]
    monkeypatch.setattr(QMessageBox,'question',lambda *args: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(session.client,'ensure_directory',lambda path:calls.append(('mkdir',path)))
    def upload(local,remote,callback,resume):
        calls.append(('upload',remote)); callback(0,4); callback(4,4)
    monkeypatch.setattr(session.client,'upload',upload); monkeypatch.setattr(session,'refresh_remote',lambda:None)
    try:
        session.upload_paths([source])
        deadline=time.monotonic()+3
        while session.pending and time.monotonic()<deadline:
            session.pump(); app.processEvents(); time.sleep(.01)
        assert session.pending==0
        assert calls==[('mkdir','/files/project'),('mkdir','/files/project/empty'),('upload','/files/project/child.txt')]
        assert session.transfers.topLevelItemCount()==3
        assert '/files/project/child.txt' in session.log.toPlainText()
    finally:
        session.timer.stop(); session.jobs.put(None); session.worker.join(3)


def test_local_pane_drag_contains_folder_and_excludes_parent(tmp_path,monkeypatch):
    import aetherftp
    from PySide6.QtWidgets import QApplication,QTreeWidgetItem
    from PySide6.QtCore import Qt
    os.environ['QT_QPA_PLATFORM']='offscreen'; app=QApplication.instance() or QApplication([])
    tree=aetherftp.FileTree(); folder=tmp_path/'project'; folder.mkdir()
    for name,path in [('..',str(tmp_path)),('project',str(folder))]:
        item=QTreeWidgetItem([name,'<DIR>']); item.setData(0,Qt.ItemDataRole.UserRole,(path,True)); tree.addTopLevelItem(item); item.setSelected(True)
    drag=Mock(); monkeypatch.setattr(aetherftp,'QDrag',Mock(return_value=drag))
    tree.startDrag(Qt.DropAction.CopyAction)
    mime=drag.setMimeData.call_args.args[0]
    assert [Path(url.toLocalFile()) for url in mime.urls()] == [folder]
    drag.exec.assert_called_once_with(Qt.DropAction.CopyAction)


def test_remote_drop_accepts_folder_url(tmp_path):
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt,QUrl,QMimeData,QPointF
    from PySide6.QtGui import QDropEvent
    from aetherftp import FileTree
    os.environ['QT_QPA_PLATFORM']='offscreen'; app=QApplication.instance() or QApplication([])
    folder=tmp_path/'project'; folder.mkdir(); upload=Mock(); tree=FileTree(upload)
    mime=QMimeData(); mime.setUrls([QUrl.fromLocalFile(str(folder))])
    event=QDropEvent(QPointF(5,5),Qt.DropAction.CopyAction | Qt.DropAction.MoveAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
    event.setDropAction(Qt.DropAction.MoveAction)
    tree.dropEvent(event)
    upload.assert_called_once_with([folder]); assert event.isAccepted()
    assert event.dropAction() == Qt.DropAction.CopyAction


def test_large_folder_queue_keeps_gui_timer_running(monkeypatch):
    import time
    import aetherftp
    from PySide6.QtWidgets import QApplication,QMessageBox
    from PySide6.QtCore import QTimer
    os.environ['QT_QPA_PLATFORM']='offscreen'; app=QApplication.instance() or QApplication([])
    session=aetherftp.Session(logging.getLogger('large-folder-test')); session.connected=True
    plan=(['/files/project'],[(f'/local/file-{i}.txt',f'/files/project/file-{i}.txt') for i in range(1000)],0)
    monkeypatch.setattr(aetherftp,'plan_uploads',lambda *args:plan)
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(session.client,'ensure_directory',lambda path:None)
    def upload(local,remote,callback,resume): callback(0,1); callback(1,1)
    monkeypatch.setattr(session.client,'upload',upload)
    refresh=Mock(); monkeypatch.setattr(session,'refresh_remote',refresh)
    seen=[]; heartbeat=QTimer(); heartbeat.setInterval(5)
    heartbeat.timeout.connect(lambda:seen.append(session.transfers.topLevelItemCount())); heartbeat.start()
    try:
        session.upload_paths(['/local/project'])
        deadline=time.monotonic()+30
        while session.pending and time.monotonic()<deadline:
            app.processEvents(); time.sleep(.001)
        assert session.pending==0
        assert session.transfers.topLevelItemCount()==1001
        assert any(0<count<1001 for count in seen), 'GUI timer must run while rows are still being created'
        assert refresh.call_count==1, 'Folder upload must refresh once, not after every file'
        assert session.log.document().blockCount()<=1000
        assert not session.upload_batches and not session.queue_timer.isActive()
    finally:
        heartbeat.stop(); session.timer.stop(); session.queue_timer.stop(); session.jobs.put(None); session.worker.join(3)
