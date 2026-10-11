import io
import json
import logging
import os
from pathlib import Path
from unittest.mock import Mock
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
    monkeypatch.setattr(transfer_client.ftplib, 'FTP_TLS', factory)
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
    def fail(): raise RuntimeError('secret-password private-host')
    session.submit(fail)
    import time
    deadline = time.monotonic() + 3
    while session.pending and time.monotonic() < deadline:
        session.pump(); time.sleep(.01)
    assert 'RuntimeError' in output.getvalue()
    assert 'secret-password' not in output.getvalue(); assert 'private-host' not in output.getvalue()
    session.timer.stop(); session.jobs.put(None); session.worker.join(1)
