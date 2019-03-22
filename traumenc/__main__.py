#!/usr/bin/env python
import os
import sys
import random
import pickle

from PyQt5.QtWidgets import (
        QMainWindow, QApplication,
        QAction, qApp, QFileDialog,
        )
from PyQt5.QtGui import (
        QIcon,
        )
from PyQt5.QtCore import (
        QSize,
        QPersistentModelIndex,
        QTimer,
        )

from engine import create_engine
from medialist import MediaListView, MediaListModel


ENGINE_POLL_INTERVAL = 200
DEFAULT_SEQUENCE_FRAMERATE = (30, 1)


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

        action_import = make_action(
            text='&Import',
            icon='import',
            tip='Import media',
            key='Ctrl+I',
            handler=self._import_media)

        action_delete = make_action(
            text='&Delete',
            icon='trash',
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
        menu.addAction(action_import)
        menu.addAction(action_quit)

        toolbar = self.addToolBar('Exit')
        for action in [action_quit, action_import, action_delete, action_encode]:
            toolbar.addAction(action)

        self._init_listview()

    def _encode_selection(self):
        print('ENCODE')

    def _delete_selection(self):
        sel = self._view.selectionModel()
        idxs = [QPersistentModelIndex(idx) for idx in sel.selectedIndexes()]
        for idx in idxs:
            self._model.removeRow(idx.row())
        idxs = None
        sel.clear()
        pass

    def _import_media(self):
        #url = QFileDialog.getExistingDirectoryUrl(self, 'Import media')
        filenames, _ = QFileDialog.getOpenFileNames(
                self,
                'Import movies',
                filter='Movies (*.mov *.avi *.mp4 *.m4v *.webm)')
        print(filenames)

    def _init_listview(self):
        self._model = MediaListModel()
        self._view = MediaListView(self)
        self._view.setModel(self._model)
        self.setCentralWidget(self._view)

    def dragEnterEvent(self, e):
        print('dragEnter')
        e.accept()

    def dropEvent(self, e):
        print('drop')
        paths = []
        for url in e.mimeData().urls():
            if url.isLocalFile():
                print(url.toLocalFile())
                paths.append(url.toLocalFile())

        print(f'''
            mime-data: {e.mimeData().formats()}
            urls: {e.mimeData().urls()}
        ''')

        self._start_scan(paths)

    def _start_scan(self, paths):
        if not paths:
            return

        self._status('Scanning...')
        self._engine.scan_paths(paths, sequence_framerate=DEFAULT_SEQUENCE_FRAMERATE)

    def _init_engine(self, engine):
        self._engine = engine
        timer = QTimer(self)
        timer.timeout.connect(self._poll_engine)
        timer.setInterval(ENGINE_POLL_INTERVAL)
        timer.start()

    def _poll_engine(self):
        """Respond to engine events.
        """
        while True:
            msg = engine.poll()
            if not msg:
                return

            if msg[0] == 'media_update':
                id = msg[1]
                data = msg[2]
                data['id'] = id
                print(msg[0], id, data.keys())
                self._model._update_item(data)

            elif msg[0] == 'scan_complete':
                print('SCAN_COMPLETE')
                self._status('Scan complete')


if __name__ == '__main__':
    app = QApplication(sys.argv)

    # start the engine
    engine = create_engine()

    # create my widgets
    main = MainWindow(engine)
    main.show()

    # start the app
    rc = app.exec_()

    # stop the engine
    engine.join()

    # quit
    sys.exit(rc)
