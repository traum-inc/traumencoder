#!/usr/bin/env python
import os
import sys
import random
import pickle

from PyQt5.QtWidgets import (
        QMainWindow, QLabel, QGridLayout, QWidget, QApplication,
        QAction, qApp, QFileDialog, QListWidget, QListWidgetItem,
        QListView,
        QStyledItemDelegate,
        QStyle,
        QStyleOptionProgressBar,
        )
from PyQt5.QtGui import (
        QImage, QIcon, QFont, QStandardItemModel, QStandardItem,
        QBrush,
        QTextDocument,
        )
from PyQt5.QtCore import (
        QSize, QRect,
        Qt, QVariant, QAbstractListModel, QPoint,
        QModelIndex, QPersistentModelIndex,
        QTimer,
        )

from engine import create_engine
from utils import format_size

ENGINE_POLL_INTERVAL = 200
DEFAULT_SEQUENCE_FRAMERATE = (30, 1)


def format_media_item(item):
    filename = item.get('filename')
    codec = item.get('codec')
    pixfmt = item.get('pixfmt')
    resolution = item.get('resolution')
    duration = item.get('duration')
    filesize = item.get('filesize')

    html = []
    if filename:
        html.append(f'<b style="font-size: 13px;">{filename}</b><br>')

    deets = []
    if codec and pixfmt:
        deets.append(f'Codec: {codec} ({pixfmt})')
    if resolution:
        deets.append(f'Resolution: {resolution[0]}x{resolution[1]}')
    if duration:
        deets.append(f'Duration: {duration:.02f}s')
    if filesize:
        deets.append(f'Size: {format_size(filesize)}')

    if deets:
        deets = '<br>'.join(deets)
        html.append(f'<div style="font-style: italic; color: gray;">{deets}</div>')

    return ''.join(html)


class MyListModel(QAbstractListModel):
    def __init__(self, parent=None):
        QAbstractListModel.__init__(self, parent)
        self._items = []

    def rowCount(self, parent):
        return len(self._items)

    def data(self, index, role):
        if not index.isValid():
            return None

        if role == Qt.DisplayRole:
            row = index.row()
            return (self._items[row])
        else:
            return None

    def removeRows(self, row, count, index):
        items = self._items
        if row < 0 or (row + count) > len(items):
            return False

        self.beginRemoveRows(index, row, row+count-1)
        self._items = items[:row] + items[row+count:]
        self.endRemoveRows()
        return True

    def _find_row_with_id(self, id):
        for row, item in enumerate(self._items):
            if item['id'] == id:
                return row
        else:
            return -1

    def _update_item(self, data):
        row = self._find_row_with_id(data['id'])
        if row < 0:
            # new item
            item = data.copy()
        else:
            # update item
            item = self._items[row]
            item.update(data)

        # (re-)create display data
        item['_html'] = format_media_item(item)

        if '_image' not in item:
            image_data = item.get('thumbnail')
            if image_data:
                image = QImage()
                image.loadFromData(image_data)
                item['_image'] = image

        # FIXME
        item['_progress'] = random.random()

        if row < 0:
            row = len(self._items)
            self.beginInsertRows(QModelIndex(), row, row)
            self._items.append(item)
            self.endInsertRows()
        else:
            index = self.index(row)
            self.dataChanged.emit(index, index, [])


class MyItemDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        QStyledItemDelegate.__init__(self, parent)

    def paint(self, painter, option, index):
        #print('paint', index)
        painter.save()
        #QStyledItemDelegate.paint(self, painter, option, index)

        #painter.setPen(Qt.blue)
        #painter.setFont(QFont('Arial', 30))
        item = index.data()

        html = item.get('_html')
        if html:
            doc = QTextDocument()
            doc.setHtml(html)
            painter.save()
            painter.translate(option.rect.topLeft())
            doc.drawContents(painter)
            painter.restore()

        image = item.get('_image')
        if image and image.width() and image.height():  # XXX
            rect = QRect(option.rect)
            rect.adjust(0, 0, 0, -1)
            aspect = float(image.width()) / image.height()
            rect.setWidth(int(rect.height() * aspect))
            rect.moveTopRight(option.rect.topRight())
            painter.drawImage(rect, image)

            progress = item.get('_progress', 0.0)
            if progress > 0.0:
                r = QRect(rect)
                r.setHeight(25)
                b = 2
                r.adjust(b, b, -b, -b)

                o = QStyleOptionProgressBar()
                o.minimum = 0
                o.maximum = 100
                o.progress = round(100 * progress)
                o.textAlignment = Qt.AlignCenter
                o.text = f'{o.progress}%'
                o.textVisible = True
                o.rect = r
                painter.setOpacity(0.75)
                qApp.style().drawControl(QStyle.CE_ProgressBar, o, painter)

        if (int(option.state) & QStyle.State_Selected) != 0:
            painter.setCompositionMode(painter.CompositionMode_Multiply)
            painter.fillRect(option.rect, option.palette.highlight())

        painter.restore()

    def sizeHint(self, option, index):
        return QSize(128, 128)


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
        view = QListView(self)
        self.setCentralWidget(view)

        model = MyListModel()
        model._data = []
        view.setModel(model)
        view.setSelectionMode(QListView.SelectionMode.ExtendedSelection)

        delegate = MyItemDelegate()
        view.setItemDelegate(delegate)

        self._view = view
        self._model = model

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
