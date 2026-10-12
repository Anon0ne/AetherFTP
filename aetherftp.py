"""AetherFTP desktop client. Project builder: Anon0ne."""
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import posixpath
import queue
import sys
import ssl
import subprocess
import threading
import uuid
import time
from collections import deque
from itertools import chain
from datetime import datetime, timezone

from PySide6.QtCore import Qt, QTimer, QMimeData, QUrl
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QLineEdit, QComboBox, QTabWidget,
    QSplitter, QTreeWidget, QTreeWidgetItem, QPlainTextEdit, QDialog,
    QFormLayout, QGridLayout, QDialogButtonBox, QMessageBox, QCheckBox, QHeaderView, QProgressBar, QAbstractItemView,
    QMenu, QSpinBox, QDoubleSpinBox, QSizePolicy, QLayout, QInputDialog)
from server_book import (load_profiles, save_profiles, encrypt_password,
    profile_password, windows_vault, STORE)
from transfer_client import Client
from version import __version__
from transfer_stats import TransferStats
from connection_url import parse_connection_url
from diagnostics import redact_message
from upload_plan import plan_uploads
from transfer_pool import TransferPool
from user_settings import DEFAULTS, load_settings, save_settings
from file_filters import FileFilter
from file_tools import load_bookmarks, save_bookmarks, server_scope, paired_paths, RemoteEdit
from local_files import read_directory, navigation_path

STYLE = '''
QWidget { background: #0b101b; color: #e4eaf5; font-family: Segoe UI; font-size: 10pt; }
QLabel, QCheckBox { background: transparent; }
QWidget#panel, QWidget#connectionBar { background: #151d2c; border-radius: 5px; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { background: #202b3c; border: 1px solid #39465c; padding: 5px; border-radius: 3px; }
QTreeWidget, QPlainTextEdit { background: #151d2c; border: none; }
QTreeWidget::item { padding: 4px 2px; }
QPushButton { background: #202b3c; border: 1px solid #39465c; padding: 6px 12px; border-radius: 3px; }
QPushButton#primary { background: #a78bfa; color: #0b101b; border: none; font-weight: 600; }
QPushButton:hover, QTabBar::tab:selected { background: #493b75; color: #e4eaf5; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPushButton:focus, QTreeWidget:focus { border: 1px solid #38bdf8; }
QHeaderView::section { background: #202b3c; color: #9caac1; border: none; padding: 6px; }
QTabBar::tab { background: #151d2c; padding: 5px 16px; margin-right: 3px; }
QTabWidget::pane { border: none; }
QSplitter#activitySplitter::handle { background: #39465c; }
QSplitter#activitySplitter::handle:hover { background: #38bdf8; }
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
        if drop is not None:
            self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.setAcceptDrops(drop is not None)
    def startDrag(self, supported_actions):
        urls = []
        for item in self.selectedItems():
            if item.text(0) == '..': continue
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data: urls.append(QUrl.fromLocalFile(data[0]))
        if not urls: return
        mime = QMimeData(); mime.setUrls(urls)
        drag = QDrag(self); drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)
    def dragEnterEvent(self, event):
        if self.drop_files and event.mimeData().hasUrls():
            event.setDropAction(Qt.DropAction.CopyAction); event.accept()
    def dragMoveEvent(self, event):
        if self.drop_files and event.mimeData().hasUrls():
            event.setDropAction(Qt.DropAction.CopyAction); event.accept()
    def dropEvent(self, event):
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        self.drop_files(paths)
        event.setDropAction(Qt.DropAction.CopyAction); event.accept()


class ActivitySplitter(QSplitter):
    """Keep the activity section within 35% of the file/activity workspace."""
    def __init__(self):
        super().__init__(Qt.Orientation.Vertical)
        self.setObjectName('activitySplitter')
        self.setHandleWidth(7)
        self.setChildrenCollapsible(False)
        self.splitterMoved.connect(self.constrain_activity)

    def setSizes(self, sizes):
        total = max(0, self.height() - self.handleWidth())
        requested = int(total * sizes[1] / max(1, sum(sizes)))
        bottom = min(requested, int(self.height() * .35))
        super().setSizes([total - bottom, bottom])

    def constrain_activity(self, position, index):
        if self.sizes()[1] > int(self.height() * .35):
            self.setSizes(self.sizes())

    def resizeEvent(self, event):
        self.update_activity_limit()
        super().resizeEvent(event)
        if self.count() == 2:
            self.constrain_activity(0, 1)

    def update_activity_limit(self):
        if self.count() == 2:
            self.widget(1).setMaximumHeight(max(1, int(self.height() * .35)))
            self.refresh()


class Session(QWidget):
    """Serialized browsing plus isolated transfer connections; GUI changes stay on the GUI thread."""
    def __init__(self, logger, pool=None):
        super().__init__()
        self.logger = logger
        self.client = Client()
        self.jobs = queue.Queue()
        self.events = queue.Queue()
        self.client.on_status = lambda message: self.events.put(('connection_step', message, datetime.now(timezone.utc).isoformat()))
        self.connection_secrets = ()
        self.connection_args = None
        self.owns_pool = pool is None
        self.transfer_pool = pool or TransferPool(Client, lambda client, ensure, job: job[0].run_transfer_job(client, ensure, job[1:]))
        self.pending = 0
        self.upload_batches = deque()
        self.progress_bars = {}
        self.connected = False
        self.local_path = Path.home()
        self.remote_path = '/'
        self.file_filter = FileFilter()
        self.sync_roots = None
        self.edits = []
        self.pending_edits = set()
        self.edit_prompt_active = False
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
        self.activity_splitter = ActivitySplitter(); layout.addWidget(self.activity_splitter, 1)
        split = QSplitter(); split.setChildrenCollapsible(False); self.activity_splitter.addWidget(split)
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
            if side == 'local':
                tree.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
                tree.setDragEnabled(True)
                tree.setToolTip('Drag selected files or folders to the remote pane to upload.')
            else:
                tree.setToolTip('Drop local files or folders here to upload into the current remote directory.')
            tree.setMinimumHeight(80)
            tree.itemDoubleClicked.connect(lambda item, col, s=side: self.open_item(s, item))
            box.addWidget(tree, 1); setattr(self, side + '_tree', tree)
            footer = QHBoxLayout(); footer.addStretch()
            transfer = QPushButton('UPLOAD  →' if side == 'local' else '←  DOWNLOAD')
            transfer.clicked.connect(self.upload_selected if side == 'local' else self.download_selected); footer.addWidget(transfer)
            box.addLayout(footer); split.addWidget(panel)
        split.setSizes([580, 580])
        activity_panel = QWidget()
        activity_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Ignored)
        activity_layout = QVBoxLayout(activity_panel); activity_layout.setContentsMargins(0, 0, 0, 0)
        activity_layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.activity_splitter.addWidget(activity_panel)
        self.activity_splitter.setStretchFactor(0, 1); self.activity_splitter.setStretchFactor(1, 0)
        self.activity_splitter.handle(1).setToolTip('Drag to resize transfer activity (maximum 35%)')
        activity_bar = QHBoxLayout()
        self.activity_toggle = QPushButton('▸ Transfer activity')
        self.activity_toggle.setCheckable(True); self.activity_toggle.toggled.connect(self.toggle_activity)
        activity_bar.addWidget(self.activity_toggle); activity_bar.addStretch()
        self.resume = QCheckBox('Resume partial files')
        self.resume.setToolTip('Use only when the destination contains the exact source prefix.')
        activity_bar.addWidget(self.resume); activity_layout.addLayout(activity_bar)
        self.activity = QTabWidget(); self.activity.setMinimumHeight(0)
        self.activity.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Ignored)
        self.transfers = QTreeWidget(); self.transfers.setHeaderLabels(['Transfer queue', 'State / progress'])
        self.transfers.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.activity.addTab(self.transfers, 'Queue')
        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.activity.addTab(self.log, 'Event log')
        self.log.setMaximumBlockCount(1000)
        activity_layout.addWidget(self.activity, 1); self.activity.hide()
        self.activity_height = 150
        self.activity_splitter.setSizes([600, 40])
        self.timer = QTimer(self); self.timer.timeout.connect(self.pump); self.timer.start(16)
        self.queue_timer = QTimer(self); self.queue_timer.setInterval(10)
        self.queue_timer.timeout.connect(self.dispatch_upload_batch)
        self.refresh_local()
        self.edit_timer = QTimer(self); self.edit_timer.setInterval(1000)
        self.edit_timer.timeout.connect(self.check_edit_changes); self.edit_timer.start()
    def toggle_activity(self, visible):
        if not visible:
            self.activity_height = self.activity_splitter.sizes()[1]
        self.activity.setVisible(visible)
        self.activity_splitter.update_activity_limit()
        self.activity_toggle.setText(('▾' if visible else '▸') + ' Transfer activity')
        total = self.activity_splitter.height()
        height = min(self.activity_height, int(total * .35)) if visible else 40
        self.activity_splitter.setSizes([max(0, total - self.activity_splitter.handleWidth() - height), height])

    def submit(self, action, success=None, row=None, operation='Operation'):
        self.pending += 1
        self.jobs.put((action, success, row, operation))
    def run_jobs(self):
        while True:
            job = self.jobs.get()
            if job is None:
                self.client.close()
                if self.owns_pool: self.transfer_pool.shutdown()
                else: self.transfer_pool.close_idle_connections()
                return
            self.run_job(*job)
    def run_job(self, action, success, row, operation, on_finished=None):
        try:
            if operation != 'Operation': self.events.put(('operation_status', operation, 'Started'))
            if row is not None: self.events.put(('state', row, 'Running'))
            result = action()
            self.events.put(('success', success, result, row))
            if operation != 'Operation': self.events.put(('operation_status', operation, 'Completed'))
        except Exception as exc:
            message = redact_message(str(exc), self.connection_secrets)
            stage = self.client.connection_stage if operation == 'Connect' else operation
            self.events.put(('error', type(exc).__name__, row, stage, message))
        finally: self.events.put(('done', on_finished))
    def run_transfer_job(self, client, ensure, job):
        action, success, row, operation, on_finished = job
        label = operation + (f' #{row + 1}' if row is not None else '')
        client.on_status = lambda message: self.events.put(('connection_step', f'{label}: {message}', datetime.now(timezone.utc).isoformat()))
        def execute():
            try: return action(client, ensure)
            except Exception:
                client.close(); raise
        self.run_job(execute, success, row, operation, on_finished)
    def pump(self):
        deadline = time.monotonic() + 0.008
        processed = 0
        while processed < 100 and time.monotonic() < deadline:
            try: event = self.events.get_nowait()
            except queue.Empty: break
            processed += 1
            if event[0] == 'done':
                self.pending -= 1
                if len(event) > 1 and event[1]: event[1]()
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
                if data['event'] == 'transfer_started' and len(event) > 3:
                    details += '\n  Remote path: ' + event[3]
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
        if self.edits:
            self.status.setText('Stop remote editing sessions before reconnecting'); return
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
        self.connection_args = args
        self.sync_roots = None
        self.connected = False
        self.status.setText('CONNECTING…')
        self.submit(lambda: self.client.connect(*args), self.on_connected, operation='Connect')
    def on_connected(self, _):
        self.connected = True; self.status.setText('CONNECTED'); self.refresh_remote()
        self.logger.info(json.dumps({'event': 'connected', 'protocol': self.protocol.currentText()}))
    def disconnect(self):
        if self.edits: self.status.setText('Stop remote editing sessions before disconnecting'); return
        if self.pending: self.status.setText('Wait for queued operations before disconnecting'); return
        self.connected = False
        self.sync_roots = None
        def close_connections():
            self.client.close(); self.transfer_pool.close_idle_connections()
        self.submit(close_connections, lambda _: self.status.setText('OFFLINE'), operation='Disconnect')
    def refresh_local(self, target=None):
        try:
            candidate = navigation_path(target or self.local_path)
            entries, skipped = read_directory(candidate)
        except OSError as error:
            self.local_display.setText(str(self.local_path))
            self.status.setText('Cannot read local directory: ' + type(error).__name__)
            return False
        self.show_local_directory(candidate, entries, skipped)
        return True

    def show_local_directory(self, path, entries, skipped):
        self.local_path = path
        self.fill(self.local_tree, entries); self.local_display.setText(str(path))
        if skipped:
            message = f'Local directory: skipped {skipped} unreadable or missing entries'
            self.status.setText(message); self.log.appendPlainText(message)
    def fill(self, tree, entries):
        tree.clear()
        for name, directory, size, path in entries:
            item = QTreeWidgetItem([name, '<DIR>' if directory else str(size)])
            item.setData(0, Qt.ItemDataRole.UserRole, (path, directory))
            tree.addTopLevelItem(item)
        self.apply_file_filters(tree)
    def refresh_remote(self, target=None, on_success=None):
        if not self.connected: return
        path = target or self.remote_display.text() or '/'
        def done(entries):
            self.remote_path = path
            self.remote_display.setText(path)
            rows = [('..', True, 0, posixpath.dirname(path.rstrip('/')) or '/')]
            rows += [(n, d, s, posixpath.join(path, n)) for n, d, s in entries]
            self.fill(self.remote_tree, rows)
            if self.url_filename:
                for item in self.remote_tree.findItems(self.url_filename, Qt.MatchFlag.MatchExactly, 0):
                    item.setSelected(True); self.remote_tree.scrollToItem(item)
                self.url_filename = ''
            if on_success: on_success()
        def listing():
            try:
                return self.client.listdir(path)
            except ssl.SSLCertVerificationError:
                raise
            except ssl.SSLError as error:
                if not self.connection_args or self.connection_args[-1] not in ('FTPES', 'FTPS'):
                    raise
                reply = redact_message(str(error), self.connection_secrets)
                self.client.step('Directory listing TLS failure: ' + reply)
                self.client.step('Reconnecting browsing connection; retrying directory listing once')
                self.client.close()
                self.client.connect(*self.connection_args)
                return self.client.listdir(path)
        self.submit(listing, done, operation='Directory listing')
    def navigate(self, side):
        if self.sync_roots:
            try:
                target = getattr(self, side + '_display').text()
                if side == 'local': target = navigation_path(target)
                local, remote = paired_paths(*self.sync_roots, side, target)
                if not local.is_dir(): raise ValueError('Matching local folder does not exist')
                entries, skipped = read_directory(local)
            except (ValueError, OSError) as error:
                self.status.setText(str(error)); self.local_display.setText(str(self.local_path)); self.remote_display.setText(self.remote_path); return
            self.local_display.setText(str(self.local_path)); self.remote_display.setText(self.remote_path)
            def paired():
                self.show_local_directory(local, entries, skipped)
            self.refresh_remote(remote, paired)
            return
        if side == 'local': self.refresh_local(self.local_display.text())
        else: self.refresh_remote()
    def open_item(self, side, item):
        path, directory = item.data(0, Qt.ItemDataRole.UserRole)
        if directory:
            getattr(self, side + '_display').setText(path); self.navigate(side)
    def enqueue_transfer(self, direction, source, dest, resume_override=None, refresh=True, barrier=None, on_finished=None, transfer_override=None, on_success=None):
        if not self.connected: self.status.setText('Connect to a server first'); return
        self.clear_finished_queue()
        resume = self.resume.isChecked() if resume_override is None else resume_override
        row = self.transfers.topLevelItemCount()
        self.transfers.addTopLevelItem(QTreeWidgetItem([direction + ': ' + Path(source).name, 'Queued']))
        bar = QProgressBar(); bar.setRange(0, 100); bar.setValue(0); bar.setMinimumHeight(28)
        bar.setAlignment(Qt.AlignmentFlag.AlignCenter); bar.setFormat('0%  •  0.00 MB/s  •  Queued')
        bar.setProperty('average_text', '0.00 MB/s')
        self.transfers.setItemWidget(self.transfers.topLevelItem(row), 1, bar)
        self.progress_bars[row] = bar
        self.activity_toggle.setChecked(True); self.activity.setCurrentIndex(0)
        transfer_id = str(uuid.uuid4())
        self.transfers.topLevelItem(row).setToolTip(0, 'Transfer ID: ' + transfer_id + '\nRemote path: ' + (str(dest) if direction == 'Upload' else str(source)))
        def record(event, **fields):
            self.events.put(('transfer_event', {'event': event, 'transfer_id': transfer_id,
                'direction': direction, 'timestamp': datetime.now(timezone.utc).isoformat(), **fields}, row,
                str(dest) if direction == 'Upload' else str(source)))
        stats = None
        last_emit = [0.0]
        previous_bytes = [None]
        def progress(done, total):
            if previous_bytes[0] is not None:
                self.transfer_pool.bandwidth[direction].consume(max(0, done - previous_bytes[0]))
            previous_bytes[0] = done
            percent, rate = stats.update(done, total)
            now = stats.clock()
            if now - last_emit[0] >= 0.1 or done == total:
                self.events.put(('progress', row, percent, rate)); last_emit[0] = now
        def transfer(client, ensure_connected):
            nonlocal stats
            stats = TransferStats()
            record('transfer_started')
            try:
                ensure_connected()
                if transfer_override:
                    transfer_override(client, progress)
                else:
                    method = client.upload if direction == 'Upload' else client.download
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
            if on_success: on_success()
            if refresh:
                self.refresh_local() if direction == 'Download' else self.refresh_remote()
        self.pending += 1
        resource = posixpath.normpath(str(dest)) if direction == 'Upload' else os.path.normcase(os.path.abspath(str(dest)))
        scope = self.connection_args[:3] + self.connection_args[4:] if direction == 'Upload' else ()
        self.transfer_pool.submit(direction, (direction, scope, resource), self.connection_args,
            (self, transfer, completed, row, direction, on_finished), barrier=barrier)
    def clear_finished_queue(self):
        # Pending includes undispatched folder work and completion callbacks.
        # Never recycle row indices while worker events can still reference them.
        if self.pending == 0 and not self.upload_batches and self.events.empty():
            self.transfers.clear()
            self.progress_bars.clear()

    def toggle_sync(self, enabled):
        if enabled and not self.connected:
            self.status.setText('Connect before enabling synchronized browsing'); return
        self.sync_roots = (self.local_path, self.remote_path) if enabled else None
        self.status.setText('Synchronized browsing enabled at current folders' if enabled else 'Synchronized browsing disabled')

    def bookmarks(self):
        if not self.connected or not self.connection_args:
            self.status.setText('Connect before using server bookmarks'); return
        scope = server_scope(self.connection_args)
        records = load_bookmarks()
        dialog = QDialog(self); dialog.setWindowTitle('Paired bookmarks'); dialog.resize(440, 180)
        form = QFormLayout(dialog); choices = QComboBox()
        matches = [r for r in records if r['scope'] == scope]
        for record in matches: choices.addItem(record['name'], record)
        form.addRow('This server', choices)
        buttons = QHBoxLayout()
        def save_current():
            name, ok = QInputDialog.getText(dialog, 'Save bookmark', 'Name')
            if not ok or not name.strip(): return
            record = dict(name=name.strip(), scope=scope, local=str(self.local_path), remote=self.remote_path)
            updated = [r for r in records if not (r['scope'] == scope and r['name'] == record['name'])] + [record]
            try: save_bookmarks(updated)
            except OSError as error: QMessageBox.warning(dialog, 'Bookmark not saved', type(error).__name__); return
            dialog.accept()
        def open_current():
            record = choices.currentData()
            if not record: return
            try: local = navigation_path(record['local'])
            except OSError as error: QMessageBox.warning(dialog, 'Bookmark unavailable', type(error).__name__); return
            if not local.is_dir(): QMessageBox.warning(dialog, 'Bookmark unavailable', 'Local folder no longer exists.'); return
            try: entries, skipped = read_directory(local)
            except OSError as error: QMessageBox.warning(dialog, 'Bookmark unavailable', type(error).__name__); return
            def opened():
                self.show_local_directory(local, entries, skipped)
                if self.sync_roots: self.sync_roots = (local, record['remote'])
            self.refresh_remote(record['remote'], opened); dialog.accept()
        def delete_current():
            record = choices.currentData()
            if not record: return
            try: save_bookmarks([r for r in records if r != record])
            except OSError as error: QMessageBox.warning(dialog, 'Bookmark not removed', type(error).__name__); return
            dialog.accept()
        for name, action in [('Save current pair', save_current), ('Open', open_current), ('Delete', delete_current)]:
            button = QPushButton(name); button.clicked.connect(action); buttons.addWidget(button)
        form.addRow(buttons); dialog.exec()

    def open_editor(self, edit):
        try:
            editor = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'notepad.exe'
            subprocess.Popen([str(editor), str(edit.path)])
        except OSError as error:
            QMessageBox.warning(self, 'Editor unavailable', type(error).__name__)

    def edit_remote_file(self):
        if not self.connected: self.status.setText('Connect before editing remote files'); return
        selected = self.remote_tree.selectedItems()
        if len(selected) != 1 or selected[0].data(0, Qt.ItemDataRole.UserRole)[1]:
            self.status.setText('Select one remote file to edit'); return
        remote = selected[0].data(0, Qt.ItemDataRole.UserRole)[0]
        if remote in self.pending_edits:
            self.status.setText('This editing download is already queued'); return
        for edit in self.edits:
            if edit.remote == remote: self.open_editor(edit); return
        folder = STORE.parent / 'editing'; folder.mkdir(parents=True, exist_ok=True)
        try: edit = RemoteEdit(remote, folder)
        except (OSError, ValueError) as error: QMessageBox.warning(self, 'Cannot edit file', str(error)); return
        def download(client, progress):
            edit.download(client, progress)
        def opened():
            self.edits.append(edit); self.open_editor(edit)
            self.status.setText('Editing ' + Path(edit.path).name + '; save in Notepad to detect changes')
        def finished():
            self.pending_edits.discard(remote)
            if edit not in self.edits: edit.close()
        self.pending_edits.add(remote)
        self.enqueue_transfer('Download', remote, str(edit.path), resume_override=False, refresh=False,
                              transfer_override=download, on_success=opened, on_finished=finished)

    def check_edit_changes(self):
        if self.pending or not self.connected or self.edit_prompt_active or QApplication.activeModalWidget(): return
        for edit in self.edits:
            try: stamp = edit.stamp()
            except OSError: continue
            if stamp == edit.last_stamp: continue
            edit.last_stamp = stamp
            self.log.appendPlainText('Editor save detected: ' + edit.path.name)
            self.edit_prompt_active = True
            try:
                if QMessageBox.question(self, 'Upload edited file', 'Upload saved changes to ' + edit.remote + '?') == QMessageBox.StandardButton.Yes:
                    self.upload_edit(edit)
            finally: self.edit_prompt_active = False
            break

    def upload_edit(self, edit):
        if not self.connected or self.pending:
            self.status.setText('Connect and wait for current operations before uploading edits'); return
        previous = [0]
        def verify(done, total):
            self.transfer_pool.bandwidth['Download'].consume(max(0, done - previous[0]))
            previous[0] = done
        def transfer(client, progress):
            edit.upload_changes(client, progress, verify)
        self.enqueue_transfer('Upload', str(edit.path), edit.remote, resume_override=False, transfer_override=transfer)

    def manage_edits(self):
        dialog = QDialog(self); dialog.setWindowTitle('Remote editing sessions')
        form = QFormLayout(dialog); choices = QComboBox()
        for edit in self.edits: choices.addItem(edit.remote, edit)
        form.addRow('File', choices)
        def action(kind):
            edit = choices.currentData()
            if not edit: return
            if kind == 'Upload changes': self.upload_edit(edit)
            elif kind == 'Reopen editor': self.open_editor(edit)
            elif self.pending:
                QMessageBox.warning(dialog, 'Operations active', 'Wait for operations before stopping editing.'); return
            elif QMessageBox.question(dialog, 'Stop editing', 'Close Notepad first. Discard this local editing copy?') == QMessageBox.StandardButton.Yes:
                try: edit.close()
                except OSError as error: QMessageBox.warning(dialog, 'Editing copy in use', type(error).__name__); return
                self.edits.remove(edit)
            dialog.accept()
        row = QHBoxLayout()
        for name in ('Upload changes', 'Reopen editor', 'Stop editing'):
            button = QPushButton(name); button.clicked.connect(lambda checked=False, name=name: action(name)); row.addWidget(button)
        form.addRow(row); dialog.exec()

    def edit_file_filters(self):
        dialog = QDialog(self); dialog.setWindowTitle('Filename filters'); dialog.resize(440, 200)
        form = QFormLayout(dialog)
        include = QLineEdit('; '.join(self.file_filter.include))
        exclude = QLineEdit('; '.join(self.file_filter.exclude))
        form.addRow('Include files', include); form.addRow('Exclude files / folders', exclude)
        note = QLabel('Separate patterns with ; (for example *.txt; *.zip).\nExclusions such as build; __pycache__; *.pyc also apply to folder uploads.\nRules apply to this tab. Folders remain navigable unless excluded.')
        note.setWordWrap(True); form.addRow(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted: return
        self.file_filter = FileFilter(include.text(), exclude.text())
        for tree in (self.local_tree, self.remote_tree):
            self.apply_file_filters(tree)

    def apply_file_filters(self, tree):
        for index in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(index)
            if item.text(0) == '..': continue
            data = item.data(0, Qt.ItemDataRole.UserRole)
            hidden = not self.file_filter.allows(item.text(0), directory=bool(data and data[1]))
            if hidden: item.setSelected(False)
            item.setHidden(hidden)

    def upload_paths(self, paths):
        if not self.connected:
            self.status.setText('Connect to a server first'); return
        paths = [Path(path) for path in paths]
        if not paths: return
        target = self.remote_path
        if not self.resume.isChecked() and QMessageBox.question(self, 'Upload files and folders',
                f'Upload {len(paths)} selected item(s) into {target}?\n'
                'Folders include their contents and empty subfolders. Existing matching files will be replaced.') != QMessageBox.StandardButton.Yes:
            return
        self.clear_finished_queue()
        self.status.setText('Preparing upload queue…')
        resume = self.resume.isChecked()
        file_filter = self.file_filter
        def ready(plan):
            directories, files, skipped = plan
            self.activity_toggle.setChecked(True); self.activity.setCurrentIndex(0)
            self.status.setText(f'Queued {len(directories)} folders and {len(files)} files; skipped {skipped} links/excluded items')
            self.log.appendPlainText(f'Upload destination: {target}\nPlanning complete: {len(directories)} folders, {len(files)} files, {skipped} links/excluded items skipped.')
            actions = chain(((None, directory) for directory in directories), iter(files))
            self.upload_batches.append({'actions': iter(actions), 'resume': resume,
                'remaining': len(files), 'barrier': threading.Event(), 'directories_ready': False,
                'dispatched': False, 'finished': False})
            # Keep the tab alive until its remaining plan has been dispatched.
            self.pending += 1
            self.queue_timer.start()
        self.submit(lambda: plan_uploads(paths, target, file_filter), ready, operation='Upload planning')
    def dispatch_upload_batch(self):
        if not self.upload_batches:
            self.queue_timer.stop(); return
        batch = self.upload_batches[0]
        deadline = time.monotonic() + 0.008
        count = 0
        while count < 20 and time.monotonic() < deadline:
            try: local, remote = next(batch['actions'])
            except StopIteration:
                self.upload_batches.popleft()
                batch['dispatched'] = True
                def release(b=batch):
                    b['barrier'].set(); self.transfer_pool.wake()
                def ready(_value, b=batch):
                    b['directories_ready'] = True; self.finish_upload_batch(b)
                self.submit(release, ready)
                if not self.upload_batches: self.queue_timer.stop()
                return
            if local is None:
                row = self.transfers.topLevelItemCount()
                self.transfers.addTopLevelItem(QTreeWidgetItem(['Create folder: ' + remote, 'Queued']))
                self.submit(lambda p=remote: self.client.ensure_directory(p), row=row, operation='Create remote folder')
            else:
                def file_finished(b=batch):
                    b['remaining'] -= 1; self.finish_upload_batch(b)
                self.enqueue_transfer('Upload', local, remote, resume_override=batch['resume'], refresh=False,
                                      barrier=batch['barrier'], on_finished=file_finished)
            count += 1
    def finish_upload_batch(self, batch):
        if batch['dispatched'] and batch['directories_ready'] and batch['remaining'] == 0 and not batch['finished']:
            batch['finished'] = True; self.pending -= 1
            self.refresh_remote()
    def upload_selected(self):
        self.upload_paths([Path(i.data(0, Qt.ItemDataRole.UserRole)[0]) for i in self.local_tree.selectedItems() if i.text(0) != '..'])
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


class SettingsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle('AetherFTP Settings'); self.resize(440, 270)
        layout = QFormLayout(self)
        self.fields = {}
        for key, label in [('uploads', 'Concurrent uploads'), ('downloads', 'Concurrent downloads')]:
            spin = QSpinBox(); spin.setRange(1, 8); spin.setValue(parent.settings[key])
            self.fields[key] = spin; layout.addRow(label, spin)
        for key, label in [('upload_mbps', 'Upload bandwidth (MB/s)'), ('download_mbps', 'Download bandwidth (MB/s)')]:
            spin = QDoubleSpinBox(); spin.setRange(0, 10000); spin.setDecimals(2)
            spin.setSpecialValueText('Unlimited'); spin.setValue(parent.settings[key])
            self.fields[key] = spin; layout.addRow(label, spin)
        note = QLabel('Limits apply across all tabs.\nLowering concurrency lets active files finish.\nBandwidth limits apply immediately; 0 means unlimited.')
        note.setWordWrap(True); layout.addRow(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self.reject); buttons.accepted.connect(self.save)
        layout.addRow(buttons)
    def save(self):
        values = {key: field.value() for key, field in self.fields.items()}
        try: save_settings(values)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Settings not saved', type(exc).__name__); return
        self.parent().settings = values
        self.parent().transfer_pool.configure(values)
        self.accept()


class App(QMainWindow):
    def __init__(self, logger):
        super().__init__(); self.logger = logger
        self.settings = load_settings()
        self.transfer_pool = TransferPool(Client, lambda client, ensure, job: job[0].run_transfer_job(client, ensure, job[1:]))
        self.transfer_pool.configure(self.settings)
        self.setWindowTitle('AetherFTP ' + __version__); self.resize(1180, 760); self.setMinimumSize(960, 600)
        root = QWidget(); layout = QVBoxLayout(root); layout.setContentsMargins(20, 16, 20, 16); layout.setSpacing(10); self.setCentralWidget(root)
        header = QHBoxLayout()
        brand = QLabel('◈ AETHER / FTP'); brand.setObjectName('brand'); header.addWidget(brand)
        caption = QLabel('ENGINEERING FILE TRANSFER'); caption.setObjectName('muted'); header.addWidget(caption)
        header.addStretch()
        credit = QLabel('Built by Anon0ne'); credit.setObjectName('muted'); header.addWidget(credit)
        self.menu_button = QPushButton('Menu ▾')
        menu = QMenu(self.menu_button)
        menu.addAction('Settings', self.open_settings)
        menu.addAction('Filename filters', lambda: self.tabs.currentWidget().edit_file_filters() if self.tabs.currentWidget() else None)
        menu.addAction('Paired bookmarks', lambda: self.tabs.currentWidget().bookmarks() if self.tabs.currentWidget() else None)
        sync = menu.addAction('Synchronized browsing'); sync.setCheckable(True)
        sync.triggered.connect(lambda checked: self.tabs.currentWidget().toggle_sync(checked) if self.tabs.currentWidget() else None)
        menu.aboutToShow.connect(lambda: sync.setChecked(bool(self.tabs.currentWidget() and self.tabs.currentWidget().sync_roots)))
        menu.addAction('Edit selected remote file', lambda: self.tabs.currentWidget().edit_remote_file() if self.tabs.currentWidget() else None)
        menu.addAction('Remote editing sessions', lambda: self.tabs.currentWidget().manage_edits() if self.tabs.currentWidget() else None)
        menu.addAction('Exit', self.close)
        self.menu_button.setMenu(menu); header.addWidget(self.menu_button)
        layout.addLayout(header)
        self.tabs = QTabWidget(); self.tabs.setTabsClosable(True); self.tabs.tabCloseRequested.connect(self.close_tab)
        button = QPushButton('+ New tab'); button.clicked.connect(self.add_tab)
        self.tabs.setCornerWidget(button, Qt.Corner.TopRightCorner); layout.addWidget(self.tabs, 1)
        self.add_tab()
    def add_tab(self):
        self.tabs.setCurrentIndex(self.tabs.addTab(Session(self.logger, self.transfer_pool), 'Connection ' + str(self.tabs.count() + 1)))
    def open_settings(self):
        SettingsDialog(self).exec()
    def close_tab(self, index):
        session = self.tabs.widget(index)
        if session.pending:
            QMessageBox.warning(self, 'Queue active', 'Wait for queued operations before closing this tab.'); return
        if session.edits:
            QMessageBox.warning(self, 'Editing active', 'Stop remote editing sessions before closing this tab.'); return
        session.timer.stop(); session.queue_timer.stop(); session.edit_timer.stop(); session.jobs.put(None); session.worker.join(timeout=1)
        self.tabs.removeTab(index); session.deleteLater()
    def closeEvent(self, event):
        if any(self.tabs.widget(i).pending or self.tabs.widget(i).edits for i in range(self.tabs.count())):
            QMessageBox.warning(self, 'Operations or editing active', 'Wait for queued operations and stop remote editing sessions before exiting.'); event.ignore(); return
        while self.tabs.count(): self.close_tab(0)
        self.transfer_pool.shutdown()
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
