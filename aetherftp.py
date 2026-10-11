"""AetherFTP desktop client. Project builder: Anon0ne."""
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import posixpath
import queue
import sys
import threading
import uuid

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QLineEdit, QComboBox, QTabWidget,
    QSplitter, QTreeWidget, QTreeWidgetItem, QPlainTextEdit, QDialog,
    QFormLayout, QGridLayout, QDialogButtonBox, QMessageBox, QCheckBox, QHeaderView)
from server_book import (load_profiles, save_profiles, encrypt_password,
    profile_password, windows_vault, STORE)
from transfer_client import Client
from version import __version__

STYLE = '''
QWidget { background: #0b101b; color: #e4eaf5; font-family: Segoe UI; font-size: 12pt; }
QLineEdit, QComboBox, QTreeWidget, QPlainTextEdit { background: #151d2c; border: 1px solid #39465c; padding: 6px; }
QPushButton { background: #202b3c; border: 1px solid #a78bfa; padding: 8px 14px; border-radius: 4px; }
QPushButton:hover, QTabBar::tab:selected { background: #493b75; }
QWidget:focus { border: 1px solid #38bdf8; }
QHeaderView::section { background: #202b3c; color: #38bdf8; padding: 6px; }
QTabBar::tab { background: #151d2c; padding: 10px; }
QTreeWidget::item:selected { background: #493b75; }
QLabel#brand { color: #a78bfa; font-size: 21pt; }
'''


def configure_logging():
    folder = STORE.parent / 'logs'
    folder.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(folder / 'aetherftp.jsonl', maxBytes=1_000_000, backupCount=3, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger = logging.getLogger('aetherftp')
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    return logger


class FileTree(QTreeWidget):
    def __init__(self, drop=None):
        super().__init__()
        self.setHeaderLabels(['Name', 'Size'])
        self.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.drop_files = drop
        self.setAcceptDrops(drop is not None)
    def dragEnterEvent(self, event):
        if self.drop_files and event.mimeData().hasUrls(): event.acceptProposedAction()
    def dragMoveEvent(self, event):
        if self.drop_files and event.mimeData().hasUrls(): event.acceptProposedAction()
    def dropEvent(self, event):
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        self.drop_files(paths)
        event.acceptProposedAction()


class Session(QWidget):
    """One serialized worker per connection; widgets only change on the GUI thread."""
    def __init__(self, logger):
        super().__init__()
        self.logger = logger
        self.client = Client()
        self.jobs = queue.Queue()
        self.events = queue.Queue()
        self.pending = 0
        self.connected = False
        self.local_path = Path.home()
        self.remote_path = '/'
        self.worker = threading.Thread(target=self.run_jobs, daemon=True)
        self.worker.start()
        layout = QVBoxLayout(self)
        form = QGridLayout()
        self.protocol = QComboBox(); self.protocol.addItems(['SFTP', 'FTPS', 'FTP'])
        self.host = QLineEdit(); self.port = QLineEdit('22')
        self.user = QLineEdit(); self.password = QLineEdit(); self.password.setEchoMode(QLineEdit.EchoMode.Password)
        for column, (name, widget) in enumerate([('Protocol', self.protocol), ('Host', self.host), ('Port', self.port), ('Username', self.user), ('Password', self.password)]):
            label = QLabel(name); label.setBuddy(widget)
            widget.setAccessibleName(name)
            form.addWidget(label, 0, column); form.addWidget(widget, 1, column)
        self.port.setMaximumWidth(100)
        self.protocol.currentTextChanged.connect(lambda value: self.port.setText('22' if value == 'SFTP' else '21'))
        layout.addLayout(form)
        bar = QHBoxLayout()
        for name, action in [('Connect', self.connect_server), ('Disconnect', self.disconnect), ('Server Book', self.server_book)]:
            button = QPushButton(name); button.clicked.connect(action); bar.addWidget(button)
        layout.addLayout(bar)
        self.status = QLabel('OFFLINE'); layout.addWidget(self.status)
        split = QSplitter(); layout.addWidget(split, 1)
        for side in ('local', 'remote'):
            panel = QWidget(); box = QVBoxLayout(panel)
            box.addWidget(QLabel(side.upper() + ' FILESYSTEM'))
            path = QLineEdit(str(self.local_path) if side == 'local' else '/')
            path.returnPressed.connect(lambda s=side: self.navigate(s))
            box.addWidget(path); setattr(self, side + '_display', path)
            tree = FileTree(self.upload_paths if side == 'remote' else None)
            tree.itemDoubleClicked.connect(lambda item, col, s=side: self.open_item(s, item))
            box.addWidget(tree); setattr(self, side + '_tree', tree)
            refresh = QPushButton('Refresh'); refresh.clicked.connect(self.refresh_local if side == 'local' else self.refresh_remote); box.addWidget(refresh)
            transfer = QPushButton('Upload selected →' if side == 'local' else '← Download selected')
            transfer.clicked.connect(self.upload_selected if side == 'local' else self.download_selected); box.addWidget(transfer)
            split.addWidget(panel)
        self.resume = QCheckBox('Resume partial files (destination must match the source prefix)')
        layout.addWidget(self.resume)
        self.transfers = QTreeWidget(); self.transfers.setHeaderLabels(['Transfer queue', 'State / progress']); self.transfers.setMaximumHeight(150)
        self.transfers.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.transfers)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMaximumHeight(90); layout.addWidget(self.log)
        self.timer = QTimer(self); self.timer.timeout.connect(self.pump); self.timer.start(50)
        self.refresh_local()
    def submit(self, action, success=None, row=None):
        self.pending += 1
        self.jobs.put((action, success, row))
    def run_jobs(self):
        while True:
            job = self.jobs.get()
            if job is None:
                self.client.close(); return
            action, success, row = job
            try:
                if row is not None: self.events.put(('state', row, 'Running'))
                result = action()
                self.events.put(('success', success, result, row))
            except Exception as exc:
                # Log types only: protocol exceptions can contain private server responses.
                self.events.put(('error', type(exc).__name__, row))
            finally: self.events.put(('done',))
    def pump(self):
        while not self.events.empty():
            event = self.events.get_nowait()
            if event[0] == 'done': self.pending -= 1
            elif event[0] == 'state': self.transfers.topLevelItem(event[1]).setText(1, event[2])
            elif event[0] == 'success':
                if event[3] is not None: self.transfers.topLevelItem(event[3]).setText(1, 'Completed')
                if event[1]: event[1](event[2])
            elif event[0] == 'error':
                self.status.setText('ERROR: ' + event[1] + ' — verify connection, paths and permissions')
                self.log.appendPlainText(self.status.text())
                self.logger.error(json.dumps({'event': 'operation_failed', 'error_type': event[1]}))
                if event[2] is not None: self.transfers.topLevelItem(event[2]).setText(1, 'Failed — requeue to retry')
    def connect_server(self):
        if self.pending:
            self.status.setText('Wait for queued operations before reconnecting'); return
        try:
            port = int(self.port.text())
            if not 1 <= port <= 65535 or not self.host.text().strip(): raise ValueError()
        except ValueError:
            self.status.setText('Enter a host and port between 1 and 65535'); return
        args = (self.host.text().strip(), port, self.user.text(), self.password.text(), self.protocol.currentText())
        self.connected = False
        self.status.setText('CONNECTING…')
        self.submit(lambda: self.client.connect(*args), self.on_connected)
    def on_connected(self, _):
        self.connected = True; self.status.setText('CONNECTED'); self.refresh_remote()
        self.logger.info(json.dumps({'event': 'connected', 'protocol': self.protocol.currentText()}))
    def disconnect(self):
        if self.pending: self.status.setText('Wait for queued operations before disconnecting'); return
        self.connected = False
        self.submit(self.client.close, lambda _: self.status.setText('OFFLINE'))
    def refresh_local(self):
        try:
            entries = [('..', True, 0, str(self.local_path.parent))]
            for p in sorted(self.local_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold())):
                entries.append((p.name, p.is_dir(), p.stat().st_size, str(p)))
            self.fill(self.local_tree, entries); self.local_display.setText(str(self.local_path))
        except OSError: self.status.setText('Cannot read local directory')
    @staticmethod
    def fill(tree, entries):
        tree.clear()
        for name, directory, size, path in entries:
            item = QTreeWidgetItem([name, '<DIR>' if directory else str(size)])
            item.setData(0, Qt.ItemDataRole.UserRole, (path, directory))
            tree.addTopLevelItem(item)
    def refresh_remote(self):
        if not self.connected: return
        path = self.remote_display.text() or '/'
        def done(entries):
            self.remote_path = path
            rows = [('..', True, 0, posixpath.dirname(path.rstrip('/')) or '/')]
            rows += [(n, d, s, posixpath.join(path, n)) for n, d, s in entries]
            self.fill(self.remote_tree, rows)
        self.submit(lambda: self.client.listdir(path), done)
    def navigate(self, side):
        if side == 'local': self.local_path = Path(self.local_display.text()).expanduser(); self.refresh_local()
        else: self.refresh_remote()
    def open_item(self, side, item):
        path, directory = item.data(0, Qt.ItemDataRole.UserRole)
        if directory:
            getattr(self, side + '_display').setText(path); self.navigate(side)
    def enqueue_transfer(self, direction, source, dest):
        if not self.connected: self.status.setText('Connect to a server first'); return
        resume = self.resume.isChecked()
        row = self.transfers.topLevelItemCount()
        self.transfers.addTopLevelItem(QTreeWidgetItem([direction + ': ' + Path(source).name, 'Queued']))
        def progress(done, total):
            self.events.put(('state', row, f'{done * 100 // total}%' if total else f'{done} bytes'))
        method = self.client.upload if direction == 'Upload' else self.client.download
        def completed(_):
            self.refresh_local() if direction == 'Download' else self.refresh_remote()
            self.logger.info(json.dumps({'event': 'transfer_completed', 'direction': direction}))
        self.submit(lambda: method(str(source), str(dest), progress, resume=resume), completed, row)
    def upload_paths(self, paths):
        for path in paths:
            if path.is_file():
                # Explicit overwrite consent also applies to files dropped from Explorer.
                if not self.resume.isChecked() and QMessageBox.question(self, 'Upload file', 'Upload this file? An existing remote file with this name will be replaced.\n' + path.name) != QMessageBox.StandardButton.Yes: continue
                self.enqueue_transfer('Upload', str(path), posixpath.join(self.remote_path, path.name))
    def upload_selected(self):
        self.upload_paths([Path(i.data(0, Qt.ItemDataRole.UserRole)[0]) for i in self.local_tree.selectedItems() if not i.data(0, Qt.ItemDataRole.UserRole)[1]])
    def download_selected(self):
        for item in self.remote_tree.selectedItems():
            source, directory = item.data(0, Qt.ItemDataRole.UserRole)
            if directory: continue
            name = posixpath.basename(source)
            if name in ('.', '..') or '/' in name or '\\' in name or ':' in name:
                self.status.setText('Unsafe remote filename'); continue
            dest = self.local_path / name
            if dest.exists() and not self.resume.isChecked() and QMessageBox.question(self, 'Replace file', 'Replace ' + name + '?') != QMessageBox.StandardButton.Yes: continue
            self.enqueue_transfer('Download', source, str(dest))
    def server_book(self):
        dialog = ServerBook(self); dialog.exec()


class ServerBook(QDialog):
    def __init__(self, session):
        super().__init__(session)
        self.session = session
        self.setWindowTitle('Server Book'); self.resize(750, 400)
        layout = QVBoxLayout(self)
        self.tree = QTreeWidget(); self.tree.setHeaderLabels(['Profile', 'Protocol', 'Host']); layout.addWidget(self.tree)
        try: self.profiles = load_profiles()
        except Exception as exc:
            QMessageBox.warning(self, 'Server Book', 'Could not load profiles: ' + type(exc).__name__)
            self.profiles = []; self.setEnabled(False)
        bar = QHBoxLayout(); layout.addLayout(bar)
        for name, action in [('New', lambda: self.edit()), ('Edit', self.edit_selected), ('Delete', self.remove), ('Load', self.load)]:
            button = QPushButton(name); button.clicked.connect(action); bar.addWidget(button)
        self.redraw()
    def redraw(self):
        self.tree.clear()
        for p in self.profiles: self.tree.addTopLevelItem(QTreeWidgetItem([p['name'], p['protocol'], p['host']]))
    def index(self):
        item = self.tree.currentItem()
        return self.tree.indexOfTopLevelItem(item) if item else None
    def edit_selected(self):
        index = self.index()
        if index is not None: self.edit(index)
    def edit(self, index=None):
        old = self.profiles[index] if index is not None else {}
        dialog = QDialog(self); dialog.setWindowTitle('Connection profile')
        layout = QFormLayout(dialog); fields = {}
        defaults = {'name': '', 'host': self.session.host.text(), 'port': self.session.port.text(), 'username': self.session.user.text(), 'local_path': str(self.session.local_path), 'remote_path': self.session.remote_path}
        for key in defaults:
            field = QLineEdit(str(old.get(key, defaults[key]))); layout.addRow(key.replace('_', ' ').title(), field); fields[key] = field
        protocol = QComboBox(); protocol.addItems(['SFTP', 'FTPS', 'FTP']); protocol.setCurrentText(old.get('protocol', self.session.protocol.currentText())); layout.addRow('Protocol', protocol)
        password = QLineEdit(); password.setEchoMode(QLineEdit.EchoMode.Password); layout.addRow('Password (blank keeps saved)', password)
        mode = QComboBox(); mode.addItems(['Do not save', 'Windows Credential Manager', 'Encrypted profile (DPAPI)'])
        mode.setCurrentIndex(1 if old.get('credential') else 2 if old.get('password_dpapi') else 0); layout.addRow('Password storage', mode)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(dialog.reject); layout.addRow(buttons)
        def save():
            try:
                item = {key: field.text().strip() for key, field in fields.items()}
                item.update(port=int(item['port']), protocol=protocol.currentText(), id=str(uuid.uuid4()))
                from server_book import validate_profiles
                updated = list(self.profiles)
                if index is None: updated.append(item)
                else: updated[index] = item
                validate_profiles(updated)
                secret = password.text() or (profile_password(old) if mode.currentIndex() else '')
                if mode.currentIndex() == 1:
                    windows_vault().set_password('AetherFTP/' + item['id'], 'password', secret); item['credential'] = 'windows'
                elif mode.currentIndex() == 2 and secret: item['password_dpapi'] = encrypt_password(secret)
                try:
                    save_profiles(updated)
                except Exception:
                    if item.get('credential'):
                        windows_vault().delete_password('AetherFTP/' + item['id'], 'password')
                    raise
                self.profiles = updated; self.redraw(); dialog.accept()
                if old.get('credential'):
                    try: windows_vault().delete_password('AetherFTP/' + old['id'], 'password')
                    except Exception:
                        QMessageBox.warning(self, 'Credential cleanup', 'Profile saved, but the previous credential could not be removed from Windows Credential Manager.')
            except Exception as exc: QMessageBox.warning(dialog, 'Profile not saved', 'Check profile fields and credential availability: ' + type(exc).__name__)
        buttons.accepted.connect(save); dialog.exec()
    def remove(self):
        index = self.index()
        if index is None or QMessageBox.question(self, 'Delete profile', 'Delete the selected profile and saved credential?') != QMessageBox.StandardButton.Yes: return
        try:
            profile = self.profiles[index]
            if profile.get('credential'): windows_vault().delete_password('AetherFTP/' + profile['id'], 'password')
            updated = self.profiles[:index] + self.profiles[index + 1:]; save_profiles(updated); self.profiles = updated; self.redraw()
        except Exception as exc: QMessageBox.warning(self, 'Delete failed', type(exc).__name__)
    def load(self):
        index = self.index()
        if index is None: return
        p = self.profiles[index]; s = self.session
        if s.pending or s.connected:
            QMessageBox.warning(self, 'Session active', 'Disconnect and finish queued work before loading a profile.'); return
        try: secret = profile_password(p)
        except Exception as exc: QMessageBox.warning(self, 'Credential unavailable', type(exc).__name__); return
        s.protocol.setCurrentText(p['protocol'])
        for widget, value in [(s.host,p['host']), (s.port,str(p['port'])), (s.user,p['username']), (s.password,secret), (s.local_display,p.get('local_path',str(Path.home()))), (s.remote_display,p.get('remote_path','/'))]: widget.setText(value)
        s.navigate('local'); self.accept()


class App(QMainWindow):
    def __init__(self, logger):
        super().__init__(); self.logger = logger
        self.setWindowTitle('AetherFTP ' + __version__); self.resize(1180, 900)
        root = QWidget(); layout = QVBoxLayout(root); self.setCentralWidget(root)
        brand = QLabel('◈ AETHER / FTP'); brand.setObjectName('brand'); layout.addWidget(brand)
        layout.addWidget(QLabel('Engineering File Transfer • Built by Anon0ne'))
        button = QPushButton('New connection tab'); button.clicked.connect(self.add_tab); layout.addWidget(button)
        self.tabs = QTabWidget(); self.tabs.setTabsClosable(True); self.tabs.tabCloseRequested.connect(self.close_tab); layout.addWidget(self.tabs)
        self.add_tab()
    def add_tab(self):
        self.tabs.setCurrentIndex(self.tabs.addTab(Session(self.logger), 'Connection ' + str(self.tabs.count() + 1)))
    def close_tab(self, index):
        session = self.tabs.widget(index)
        if session.pending:
            QMessageBox.warning(self, 'Queue active', 'Wait for queued operations before closing this tab.'); return
        session.timer.stop(); session.jobs.put(None); session.worker.join(timeout=1)
        self.tabs.removeTab(index); session.deleteLater()
    def closeEvent(self, event):
        if any(self.tabs.widget(i).pending for i in range(self.tabs.count())):
            QMessageBox.warning(self, 'Queue active', 'Wait for queued operations before exiting.'); event.ignore(); return
        while self.tabs.count(): self.close_tab(0)
        event.accept()


def main():
    app = QApplication(sys.argv); app.setStyle('Fusion'); app.setStyleSheet(STYLE)
    logger = configure_logging()
    def exception_hook(kind, value, traceback):
        logger.error(json.dumps({'event': 'unhandled_exception', 'error_type': kind.__name__}))
        QMessageBox.critical(None, 'AetherFTP error', 'An unexpected error occurred: ' + kind.__name__)
    sys.excepthook = exception_hook
    window = App(logger); window.show()
    if '--smoke-test' in sys.argv: QTimer.singleShot(500, window.close)
    return app.exec()


if __name__ == '__main__': sys.exit(main())
