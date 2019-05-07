import logging

from PyQt5.QtWidgets import (
        QMainWindow, QAction, QFileDialog, QComboBox, QLabel,
        QWidget, QSizePolicy,
        qApp,
        )
from PyQt5.QtGui import (
        QIcon,
        )
from PyQt5.QtCore import (
        Qt, QSize, QTimer, QPersistentModelIndex,
        )

from medialist import MediaListView, MediaListModel
from encodingprofiles import encoding_profiles, framerates
from config import config


log = logging.getLogger('app')


icon_cache = {}
def get_icon(name):
    if name not in icon_cache:
        filename = f'icons/{name}.png'
        icon_cache[name] = QIcon(filename)
    return icon_cache[name]


class MainWindow(QMainWindow):
    def __init__(self, engine):
        QMainWindow.__init__(self)
        self._init_engine(engine)
        self._init_ui()
        self._is_scanning = False
        self._is_encoding = False

    def _status(self, message):
        self.statusBar().showMessage(message)

    def _init_ui(self):
        self.setMinimumSize(QSize(640, 480))
        self.setWindowTitle('traumEnc')

        self.setAcceptDrops(True)
        self._status('Ready')

        def make_action(text, icon, tip=None, key=None, handler=None):
            action = QAction(get_icon(icon), text, self)
            if key:
                action.setShortcut(key)
            if tip:
                action.setStatusTip(tip)
            if handler:
                action.triggered.connect(handler)
            return action

        action_quit = make_action(
            text='&Exit',
            icon='exit',
            tip='Exit application',
            key='Ctrl+Q',
            handler=qApp.quit)

        action_import_videos = make_action(
            text='&Add Videos',
            icon='import',
            tip='Add videos',
            key='Ctrl+I',
            handler=self._import_media_videos)

        action_import_folder = make_action(
            text='&Add Folder',
            icon='import',
            tip='Add folder',
            key='Ctrl+I',
            handler=self._import_media_folder)

        action_cancel_scan = make_action(
            text='&Stop Scan',
            icon='exit',
            tip='Stop scanning folders',
            handler=self._cancel_scan)
        self._action_cancel_scan = action_cancel_scan

        action_delete = make_action(
            text='&Delete',
            icon='trash',
            key='Delete',
            tip='Delete selection',
            handler=self._delete_selection)

        action_encode = make_action(
            text='&Encode',
            icon='gears',
            tip='Encode selection or all',
            key='Ctrl+E',
            handler=self._encode_or_cancel)
        self._action_encode = action_encode

        menubar = self.menuBar()

        menu = menubar.addMenu('&File')
        menu.addAction(action_import_videos)
        menu.addAction(action_import_folder)
        menu.addSeparator()
        menu.addAction(action_quit)

        menu = menubar.addMenu('&Edit')
        menu.addAction(action_delete)

        toolbar = self.addToolBar('Exit')
        for action in [action_import_videos, action_import_folder]:
            toolbar.addAction(action)
        toolbar.addSeparator()
        action_cancel_scan.setEnabled(False)
        toolbar.addAction(action_cancel_scan)

        toolbar.addSeparator()

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        toolbar.addWidget(spacer)

        combo = QComboBox()
        framerate_ids = list(framerates.keys())
        for framerate_id in framerate_ids:
            framerate = framerates[framerate_id]
            combo.addItem(framerate['label'], userData=framerate_id)
        combo.setCurrentIndex(framerate_ids.index('fps_30'))
        self._combo_framerate = combo

        #toolbar.addWidget(QLabel('Rate:'))
        toolbar.addWidget(combo)


        combo = QComboBox()
        profile_ids = list(encoding_profiles)
        for profile_id in profile_ids:
            profile = encoding_profiles[profile_id]
            combo.addItem(profile['label'], userData=profile_id)
        combo.setCurrentIndex(profile_ids.index('prores_422'))
        self._combo_profile = combo
        #toolbar.addWidget(QLabel('Profile:'))
        toolbar.addWidget(combo)

        toolbar.addAction(action_encode)

        toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)

        self._init_listview()

    def _get_selected_media_ids(self, clear=False):
        sel = self._view.selectionModel()
        media_ids = []
        for idx in sel.selectedIndexes():
            media_id = self._model.get_media_id_for_index(idx)
            media_ids.append(media_id)
        if clear:
            sel.clear()
        return media_ids

    def _encode_or_cancel(self):
        if self._is_encoding:
            log.debug('cancelling encode')
            self._engine.cancel_encode()
        else:
            if self._encode_selection():
                self._set_encoding_state(True)

    def _set_encoding_state(self, encoding):
        self._is_encoding = encoding
        action = self._action_encode
        if encoding:
            action.setIcon(get_icon('exit'))
            action.setText('Cancel')
        else:
            action.setIcon(get_icon('gears'))
            action.setText('Encode')

    def _encode_selection(self):
        if self._is_scanning:
            return

        media_ids = self._get_selected_media_ids(True)
        profile = self._combo_profile.currentData()
        framerate = self._combo_framerate.currentData()
        log.info(f'encode selection: {profile} {framerate}, {len(media_ids)} items')
        self._status(f'Encoding {len(media_ids)} items...')
        self._engine.encode_items(ids=media_ids, profile=profile, framerate=framerate)
        return True

    def _delete_selection(self):
        log.info('delete selection')
        media_ids = self._get_selected_media_ids(True)
        if media_ids:
            self._engine.remove_items(media_ids)

        # sel = self._view.selectionModel()
        # idxs = [QPersistentModelIndex(idx) for idx in sel.selectedIndexes()]
        # for idx in idxs:
        #     self._model.removeRow(idx.row())
        # idxs = None
        # sel.clear()

    def _import_media_videos(self):
        filenames, _ = QFileDialog.getOpenFileNames(
                self,
                'Import videos',
                filter='Videos (*.mov *.avi *.mp4 *.m4v *.webm)')
        log.info(f'import: {filenames}')
        if filenames:
            self._start_scan(filenames)

    def _import_media_folder(self):
        dirpath = QFileDialog.getExistingDirectory(
                self,
                'Import folder',
                options=QFileDialog.ShowDirsOnly)
        log.info(f'import_media_folder: {dirpath}')
        if dirpath:
            self._start_scan([dirpath])

    def _cancel_scan(self):
        if self._is_scanning:
            log.info('cancelling scan')
            self._engine.cancel_scan()

    def _init_listview(self):
        self._model = MediaListModel()
        self._view = MediaListView(self)
        self._view.setModel(self._model)
        self.setCentralWidget(self._view)
        self._view.doubleClicked.connect(self._preview_item)

    def _preview_item(self, idx):
        media_id = self._model.get_media_id_for_index(idx)
        log.info(f'preview item {media_id}')
        framerate = self._combo_framerate.currentData()
        self._engine.preview_item(media_id, framerate)

    def dragEnterEvent(self, e):
        e.accept()

    def dropEvent(self, e):
        paths = []
        for url in e.mimeData().urls():
            if url.isLocalFile():
                paths.append(url.toLocalFile())

        self._start_scan(paths)

    def _start_scan(self, paths):
        if self._is_encoding:
            return

        if not paths:
            return

        self._status('Scanning...')

        sequence_framerate_id = self._combo_framerate.currentData()
        sequence_framerate = framerates[sequence_framerate_id]['rate']
        self._engine.scan_paths(paths, sequence_framerate)
        self._is_scanning = True
        self._action_cancel_scan.setEnabled(True)

    def _init_engine(self, engine):
        self._engine = engine
        timer = QTimer(self)
        timer.timeout.connect(self._poll_engine)
        timer.setInterval(config['ui'].getint('engine_poll_interval'))
        timer.start()

    def _poll_engine(self):
        """Respond to engine events.
        """
        while True:
            msg = self._engine.poll()
            if msg:
                event, args = msg[0], msg[1:]
                self._dispatch_engine_event(event, args)
            else:
                break

    def _dispatch_engine_event(self, event, args):
        """Dispatch event to handler if one exists.
        """
        handler = getattr(self, f'_on_engine_{event}', None)
        if handler:
            handler(*args)
        else:
            log.warn(f'unhandled engine event: {event} {args}')

    def _on_engine_media_update(self, id, data):
        #log.debug(f'media_update {id} ({",".join(data.keys())})')
        data['id'] = id
        self._model._update_item(data)

    def _on_engine_media_delete(self, id):
        log.debug(f'media_delete {id}')
        self._model._remove_item_by_id(id)

    def _on_engine_scan_update(self, dirs, files):
        log.debug(f'scan_update: {dirs} dirs, {files} files')
        self._status(f'Scanning {dirs} folders, {files} files...')

    def _on_engine_scan_complete(self):
        log.debug('scan_complete')
        self._status('Scan complete')
        self._is_scanning = False
        self._action_cancel_scan.setEnabled(False)

    def _on_engine_scan_cancelled(self):
        log.debug('scan_cancelled')
        self._status('Scan cancelled')
        self._is_scanning = False
        self._action_cancel_scan.setEnabled(False)

    def _on_engine_encode_cancelled(self):
        log.debug('encode_cancelled')
        self._status('Encode cancelled')
        self._set_encoding_state(False)

    def _on_engine_encode_complete(self):
        log.debug('encode_complete')
        self._status('Encode complete')
        self._set_encoding_state(False)
