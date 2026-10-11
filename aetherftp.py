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
from datetime import datetime, timezone

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QLineEdit, QComboBox, QTabWidget,
    QSplitter, QTreeWidget, QTreeWidgetItem, QPlainTextEdit, QDialog,
    QFormLayout, QGridLayout, QDialogButtonBox, QMessageBox, QCheckBox, QHeaderView, QProgressBar)
from server_book import (load_profiles, save_profiles, encrypt_password,
    profile_password, windows_vault, STORE)
from transfer_client import Client
from version import __version__
from transfer_stats import TransferStats
from connection_url import parse_connection_url
from diagnostics import redact_message

STYLE = '''
QWidget { background: #0b101b; color: #e4eaf5; font-family: Segoe UI; font-size: 10pt; }
QLabel, QCheckBox { background: transparent; }
QWidget#panel, QWidget#connectionBar { background: #151d2c; border-radius: 5px; }
QLineEdit, QComboBox { background: #202b3c; border: 1px solid #39465c; padding: 5px; border-radius: 3px; }
QTreeWidget, QPlainTextEdit { background: #151d2c; border: none; }
QTreeWidget::item { padding: 4px 2px; }
QPushButton { background: #202b3c; border: 1px solid #39465c; padding: 6px 12px; border-radius: 3px; }
QPushButton#primary { background: #a78bfa; color: #0b101b; border: none; font-weight: 600; }
QPushButton:hover, QTabBar::tab:selected { background: #493b75; color: #e4eaf5; }
QLineEdit:focus, QComboBox:focus, QPushButton:focus, QTreeWidget:focus { border: 1px solid #38bdf8; }
QHeaderView::section { background: #202b3c; color: #9caac1; border: none; padding: 6px; }
QTabBar::tab { background: #151d2c; padding: 5px 16px; margin-right: 3px; }
QTabWidget::pane { border: none; }
QTreeWidget::item:selected { background: #493b75; }
QLabel#brand { color: #a78bfa; font-size: 20pt; font-weight: 600; }
QLabel#muted { color: #9caac1; }
QLabel#localHeading { color: #38bdf8; font-weight: 600; }
QLabel#remoteHeading { color: #a78bfa; font-weight: 600; }
QProgressBar { background: #0b101b; color: #ffffff; border: 1px solid #58677e; border-radius: 4px; text-align: center; font-weight: 600; }
QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #594184, stop:1 #146a7c); border-radius: 3px; }
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
        self.client.on_status = lambda message: self.events.put(('connection_step', message, datetime.now(timezone.utc).isoformat()))
        self.connection_secrets = ()
        self.pending = 0
        self.progress_bars = {}
        self.connected = False
        self.local_path = Path.home()
        self.remote_path = '/'
        self.url_filename = ''
        self.worker = threading.Thread(target=self.run_jobs, daemon=True)
        self.worker.start()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0); layout.setSpacing(8)
        connection = QWidget(); connection.setObjectName('connectionBar')
        form = QHBoxLayout(connection); form.setContentsMargins(10, 8, 10, 8); form.setSpacing(8)
        self.protocol = QComboBox(); self.protocol.addItems(['SFTP', 'FTPES', 'FTPS', 'FTP'])
        self.protocol.setToolTip('FTPES and legacy FTPS use explicit TLS (AUTH TLS), not implicit TLS.')
        self.host = QLineEdit(); self.port = QLineEdit('22')
        self.host.setPlaceholderText('Host or ftpes:// URL')
        self.host.editingFinished.connect(self.load_connection_url)
        self.user = QLineEdit(); self.password = QLineEdit(); self.password.setEchoMode(QLineEdit.EchoMode.Password)
        for name, widget, stretch in [('Protocol', self.protocol, 0), ('Host / IP', self.host, 2), ('Port', self.port, 0), ('Username', self.user, 1), ('Password', self.password, 1)]:
            field = QVBoxLayout(); field.setSpacing(3)
            label = QLabel(name); label.setObjectName('muted'); label.setBuddy(widget)
            widget.setAccessibleName(name)
            field.addWidget(label); field.addWidget(widget); form.addLayout(field, stretch)
        self.protocol.setFixedWidth(90); self.port.setFixedWidth(58)
        self.host.setMinimumWidth(120); self.user.setMinimumWidth(85); self.password.setMinimumWidth(85)
        self.protocol.currentTextChanged.connect(lambda value: self.port.setText('22' if value == 'SFTP' else '21'))
        for name, action in [('Server Book', self.server_book), ('Connect', self.connect_server), ('Disconnect', self.disconnect)]:
            button = QPushButton(name); button.clicked.connect(action)
            if name == 'Connect': button.setObjectName('primary')
            form.addWidget(button, 0, Qt.AlignmentFlag.AlignBottom)
        layout.addWidget(connection)
        self.status = QLabel('● OFFLINE'); self.status.setObjectName('muted'); layout.addWidget(self.status)
        split = QSplitter(); split.setChildrenCollapsible(False); layout.addWidget(split, 1)
        self.file_splitter = split
        for side in ('local', 'remote'):
            panel = QWidget(); panel.setObjectName('panel')
            box = QVBoxLayout(panel); box.setContentsMargins(10, 10, 10, 10); box.setSpacing(8)
            heading = QHBoxLayout()
            title = QLabel('◧  ' + side.upper() + ' FILESYSTEM'); title.setObjectName(side + 'Heading'); heading.addWidget(title)
            heading.addStretch()
            refresh = QPushButton('↻'); refresh.setToolTip('Refresh ' + side + ' files'); refresh.setAccessibleName('Refresh ' + side + ' files')
            refresh.clicked.connect(self.refresh_local if side == 'local' else self.refresh_remote); heading.addWidget(refresh)
            box.addLayout(heading)
            path = QLineEdit(str(self.local_path) if side == 'local' else '/')
            path.setAccessibleName(side.title() + ' directory')
            path.returnPressed.connect(lambda s=side: self.navigate(s))
            box.addWidget(path); setattr(self, side + '_display', path)
            tree = FileTree(self.upload_paths if side == 'remote' else None)
            tree.setMinimumHeight(80)
            tree.itemDoubleClicked.connect(lambda item, col, s=side: self.open_item(s, item))
            box.addWidget(tree, 1); setattr(self, side + '_tree', tree)
            footer = QHBoxLayout(); footer.addStretch()
            transfer = QPushButton('UPLOAD  →' if side == 'local' else '←  DOWNLOAD')
            transfer.clicked.connect(self.upload_selected if side == 'local' else self.download_selected); footer.addWidget(transfer)
            box.addLayout(footer); split.addWidget(panel)
        split.setSizes([580, 580])
        activity_bar = QHBoxLayout()
        self.activity_toggle = QPushButton('▸ Transfer activity')
        self.activity_toggle.setCheckable(True); self.activity_toggle.toggled.connect(self.toggle_activity)
        activity_bar.addWidget(self.activity_toggle); activity_bar.addStretch()
        self.resume = QCheckBox('Resume partial files')
        self.resume.setToolTip('Use only when the destination contains the exact source prefix.')
        activity_bar.addWidget(self.resume); layout.addLayout(activity_bar)
        self.activity = QTabWidget(); self.activity.setFixedHeight(110)
        self.transfers = QTreeWidget(); self.transfers.setHeaderLabels(['Transfer queue', 'State / progress'])
        self.transfers.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.activity.addTab(self.transfers, 'Queue')
        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.activity.addTab(self.log, 'Event log')
        layout.addWidget(self.activity); self.activity.hide()
        self.timer = QTimer(self); self.timer.timeout.connect(self.pump); self.timer.start(50)
        self.refresh_local()
    def toggle_activity(self, visible):
        self.activity.setVisible(visible)
        self.activity_toggle.setText(('▾' if visible else '▸') + ' Transfer activity')

    def submit(self, action, success=None, row=None, operation='Operation'):
        self.pending += 1
        self.jobs.put((action, success, row, operation))
    def run_jobs(self):
        while True:
            job = self.jobs.get()
            if job is None:
                self.client.close(); return
            action, success, row, operation = job
            try:
                if operation != 'Operation': self.events.put(('operation_status', operation, 'Started'))
                if row is not None: self.events.put(('state', row, 'Running'))
                result = action()
                self.events.put(('success', success, result, row))
                if operation != 'Operation': self.events.put(('operation_status', operation, 'Completed'))
            except Exception as exc:
                # Real replies are useful, but authentication values must never enter logs.
                message = redact_message(str(exc), self.connection_secrets)
                stage = self.client.connection_stage if operation == 'Connect' else operation
                self.events.put(('error', type(exc).__name__, row, stage, message))
            finally: self.events.put(('done',))
    def pump(self):
        while not self.events.empty():
            event = self.events.get_nowait()
            if event[0] == 'done': self.pending -= 1
            elif event[0] == 'connection_step':
                self.log.appendPlainText(event[2] + '  ' + event[1])
                self.logger.info(json.dumps({'event': 'connection_step', 'timestamp': event[2], 'stage': event[1]}))
            elif event[0] == 'operation_status':
                stamp = datetime.now(timezone.utc).isoformat()
                self.log.appendPlainText(stamp + '  ' + event[1] + ': ' + event[2])
                self.logger.info(json.dumps({'event': 'operation_status', 'timestamp': stamp, 'operation': event[1], 'status': event[2]}))
            elif event[0] == 'state': self.set_transfer_state(event[1], event[2])
            elif event[0] == 'progress':
                bar = self.progress_bars[event[1]]
                percent, rate = event[2], event[3]
                bar.setValue(percent or 0)
                bar.setFormat(f'{percent if percent is not None else "—"}%  •  {rate:.2f} MB/s')
            elif event[0] == 'transfer_event':
                data = event[1]
                self.logger.info(json.dumps(data))
                stamp = datetime.fromisoformat(data['timestamp']).astimezone().strftime('%H:%M:%S')
                label = self.transfers.topLevelItem(event[2]).text(0)
                details = f"{stamp}  {label}  [{data['transfer_id'][:8]}]  {data['event'].removeprefix('transfer_')}"
                if 'duration_seconds' in data:
                    details += f"  | {data['duration_seconds']:.3f} s | {data['average_mbps']:.2f} MB/s | {data['bytes_transferred']} bytes"
                self.log.appendPlainText(details)
            elif event[0] == 'success':
                if event[3] is not None: self.set_transfer_state(event[3], 'Completed')
                if event[1]: event[1](event[2])
            elif event[0] == 'error':
                self.status.setText('ERROR: ' + event[3] + ' — ' + event[1] + ' (see Event log)')
                stamp = datetime.now(timezone.utc).isoformat()
                self.log.appendPlainText(stamp + '  ' + self.status.text() + '\n' + event[4])
                self.logger.error(json.dumps({'event': 'operation_failed', 'timestamp': stamp,
                    'error_type': event[1], 'stage': event[3], 'message': event[4]}))
                self.activity_toggle.setChecked(True); self.activity.setCurrentIndex(1)
                if event[2] is not None: self.set_transfer_state(event[2], 'Failed')
    def set_transfer_state(self, row, state):
        bar = self.progress_bars.get(row)
        if bar is None:
            self.transfers.topLevelItem(row).setText(1, state)
            return
        if state == 'Completed':
            bar.setValue(100)
            bar.setFormat('100%  •  ' + bar.property('average_text') + '  •  Completed')
        elif state == 'Failed':
            bar.setFormat(f'{bar.value()}%  •  Failed — requeue to retry')
        else:
            if state == 'Running': self.transfers.scrollToItem(self.transfers.topLevelItem(row))
            bar.setFormat('0%  •  0.00 MB/s  •  ' + state)
    def load_connection_url(self):
        if '://' not in self.host.text(): return True
        if self.pending or self.connected:
            self.status.setText('Disconnect and finish queued work before loading a URL'); return False
        try:
            values = parse_connection_url(self.host.text())
        except ValueError:
            self.status.setText('Invalid connection URL. Use a host, optional user/port and path; enter passwords separately.')
            return False
        self.protocol.setCurrentText(values['protocol'])
        self.host.setText(values['host']); self.port.setText(str(values['port']))
        self.user.setText(values['username']); self.password.clear()
        self.remote_path = values['remote_path']; self.remote_display.setText(self.remote_path)
        self.url_filename = values['filename']
        self.status.setText('URL loaded — enter your password, then Connect')
        return True

    def connect_server(self):
        if not self.load_connection_url(): return
        if self.pending:
            self.status.setText('Wait for queued operations before reconnecting'); return
        try:
            port = int(self.port.text())
            if not 1 <= port <= 65535 or not self.host.text().strip(): raise ValueError()
        except ValueError:
            self.status.setText('Enter a host and port between 1 and 65535'); return
        args = (self.host.text().strip(), port, self.user.text(), self.password.text(), self.protocol.currentText())
        self.connection_secrets = tuple(value for value in args[:1] + args[2:4] if value)
        self.connected = False
        self.status.setText('CONNECTING…')
        self.submit(lambda: self.client.connect(*args), self.on_connected, operation='Connect')
    def on_connected(self, _):
        self.connected = True; self.status.setText('CONNECTED'); self.refresh_remote()
        self.logger.info(json.dumps({'event': 'connected', 'protocol': self.protocol.currentText()}))
    def disconnect(self):
        if self.pending: self.status.setText('Wait for queued operations before disconnecting'); return
        self.connected = False
        self.submit(self.client.close, lambda _: self.status.setText('OFFLINE'), operation='Disconnect')
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
            if self.url_filename:
                for item in self.remote_tree.findItems(self.url_filename, Qt.MatchFlag.MatchExactly, 0):
                    item.setSelected(True); self.remote_tree.scrollToItem(item)
                self.url_filename = ''
        self.submit(lambda: self.client.listdir(path), done, operation='Directory listing')
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
        bar = QProgressBar(); bar.setRange(0, 100); bar.setValue(0); bar.setMinimumHeight(28)
        bar.setAlignment(Qt.AlignmentFlag.AlignCenter); bar.setFormat('0%  •  0.00 MB/s  •  Queued')
        bar.setProperty('average_text', '0.00 MB/s')
        self.transfers.setItemWidget(self.transfers.topLevelItem(row), 1, bar)
        self.progress_bars[row] = bar
        self.activity_toggle.setChecked(True); self.activity.setCurrentIndex(0)
        transfer_id = str(uuid.uuid4())
        self.transfers.topLevelItem(row).setToolTip(0, 'Transfer ID: ' + transfer_id)
        def record(event, **fields):
            self.events.put(('transfer_event', {'event': event, 'transfer_id': transfer_id,
                'direction': direction, 'timestamp': datetime.now(timezone.utc).isoformat(), **fields}, row))
        stats = None
        last_emit = [0.0]
        def progress(done, total):
            percent, rate = stats.update(done, total)
            now = stats.clock()
            if now - last_emit[0] >= 0.1 or done == total:
                self.events.put(('progress', row, percent, rate)); last_emit[0] = now
        method = self.client.upload if direction == 'Upload' else self.client.download
        def transfer():
            nonlocal stats
            stats = TransferStats()
            record('transfer_started')
            try:
                method(str(source), str(dest), progress, resume=resume)
            except Exception as exc:
                record('transfer_failed', error_type=type(exc).__name__, **stats.summary())
                raise
            summary = stats.summary()
            record('transfer_completed', **summary)
            return summary
        def completed(summary):
            bar.setProperty('average_text', f'{summary["average_mbps"]:.2f} MB/s')
            self.set_transfer_state(row, 'Completed')
            self.refresh_local() if direction == 'Download' else self.refresh_remote()
        self.submit(transfer, completed, row, operation=direction)
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
        protocol = QComboBox(); protocol.addItems(['SFTP', 'FTPES', 'FTPS', 'FTP']); protocol.setCurrentText(old.get('protocol', self.session.protocol.currentText())); layout.addRow('Protocol', protocol)
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
        self.setWindowTitle('AetherFTP ' + __version__); self.resize(1180, 760); self.setMinimumSize(960, 600)
        root = QWidget(); layout = QVBoxLayout(root); layout.setContentsMargins(20, 16, 20, 16); layout.setSpacing(10); self.setCentralWidget(root)
        header = QHBoxLayout()
        brand = QLabel('◈ AETHER / FTP'); brand.setObjectName('brand'); header.addWidget(brand)
        caption = QLabel('ENGINEERING FILE TRANSFER'); caption.setObjectName('muted'); header.addWidget(caption)
        header.addStretch()
        credit = QLabel('Built by Anon0ne'); credit.setObjectName('muted'); header.addWidget(credit)
        layout.addLayout(header)
        self.tabs = QTabWidget(); self.tabs.setTabsClosable(True); self.tabs.tabCloseRequested.connect(self.close_tab)
        button = QPushButton('+ New tab'); button.clicked.connect(self.add_tab)
        self.tabs.setCornerWidget(button, Qt.Corner.TopRightCorner); layout.addWidget(self.tabs, 1)
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
