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
import config


log = logging.getLogger('app')


class MainWindow(QMainWindow):
    def __init__(self, engine):
        QMainWindow.__init__(self)
        self._init_engine(engine)
        self._init_ui()

    def _status(self, message):
        self.statusBar().showMessage(message)

    def _init_ui(self):
        self.setMinimumSize(QSize(640, 480))
        self.setWindowTitle('traumEnc')

        self.setAcceptDrops(True)
        self._status('Ready')

        def make_action(text, icon, tip=None, key=None, handler=None):
            action = QAction(QIcon(f'icons/{icon}.png'), text, self)
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
            handler=self._encode_selection)

        menubar = self.menuBar()
        menu = menubar.addMenu('&File')
        menu.addAction(action_import_videos)
        menu.addAction(action_import_folder)
        menu.addAction(action_quit)

        menu = menubar.addMenu('&Edit')
        menu.addAction(action_delete)

        toolbar = self.addToolBar('Exit')
        for action in [action_import_videos, action_import_folder]:
            toolbar.addAction(action)

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

    def _encode_selection(self):
        log.info('encode selection')
        media_ids = self._get_selected_media_ids(True)
        if media_ids:
            self._status(f'Encoding {len(media_ids)} items...')
            self._engine.encode_items(media_ids)

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

    def _import_media_folder(self):
        dirpath = QFileDialog.getExistingDirectory(
                self,
                'Import folder')
        log.info(f'import_media_folder: {dirpath}')
        if dirpath:
            self._start_scan([dirpath])

    def _init_listview(self):
        self._model = MediaListModel()
        self._view = MediaListView(self)
        self._view.setModel(self._model)
        self.setCentralWidget(self._view)

    def dragEnterEvent(self, e):
        e.accept()

    def dropEvent(self, e):
        paths = []
        for url in e.mimeData().urls():
            if url.isLocalFile():
                paths.append(url.toLocalFile())

        self._start_scan(paths)

    def _start_scan(self, paths):
        if not paths:
            return

        self._status('Scanning...')
        self._engine.scan_paths(paths,
                sequence_framerate=config.DEFAULT_SEQUENCE_FRAMERATE)

    def _init_engine(self, engine):
        self._engine = engine
        timer = QTimer(self)
        timer.timeout.connect(self._poll_engine)
        timer.setInterval(config.ENGINE_POLL_INTERVAL)
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
        log.debug(f'media_update {id} ({",".join(data.keys())})')
        data['id'] = id
        self._model._update_item(data)

    def _on_engine_media_delete(self, id):
        log.debug(f'media_delete {id}')
        self._model._remove_item_by_id(id)

    def _on_engine_scan_complete(self):
        log.debug('scan_complete')
        self._status('Scan complete')

