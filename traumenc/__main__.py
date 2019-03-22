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


def sizeof_fmt(num, suffix='B'):
    for unit in ['','Ki','Mi','Gi','Ti','Pi','Ei','Zi']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)


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
        deets.append(f'Size: {sizeof_fmt(filesize)}')

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
        if 0 <= row and (row + count) <= len(data):
            self.beginRemoveRows(index, row, row+count-1)
            self._items = items[:row] + items[row+count:]
            self.endRemoveRows()
            return True
        else:
            return False

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


class HelloWindow(QMainWindow):
    def __init__(self):
        QMainWindow.__init__(self)
        self.setMinimumSize(QSize(640, 480))
        self.setWindowTitle('traumEnc')

        self.setAcceptDrops(True)
        self.statusBar().showMessage('Ready...')

        action = QAction(QIcon('icons/exit.png'), '&Exit', self)
        action.setShortcut('Ctrl+Q')
        action.setStatusTip('Exit application')
        action.triggered.connect(qApp.quit)

        action2 = QAction(QIcon('icons/import.png'), '&Import', self)
        action2.setShortcut('Ctrl+I')
        action2.setStatusTip('Import media')
        action2.triggered.connect(self.import_media)

        action3 = QAction(QIcon('icons/trash.png'), '&Delete', self)
        action3.setShortcut('Delete')
        action3.setStatusTip('Delete selection')
        action3.triggered.connect(self.delete_selection)

        action4 = QAction(QIcon('icons/gears.png'), '&Encode', self)
        action4.setShortcut('Ctrl+E')
        action4.setStatusTip('Encode all/selection')
        action4.triggered.connect(self.encode_selection)

        menubar = self.menuBar()
        menu = menubar.addMenu('&File')
        menu.addAction(action2)
        menu.addAction(action)

        toolbar = self.addToolBar('Exit')
        toolbar.addAction(action)
        toolbar.addAction(action2)
        toolbar.addAction(action3)
        toolbar.addAction(action4)

        # ---
        self.init_listview2()

        # QTreeView, QTreeWidget
        # QListView, QListWidget

        #title = QLabel('Hello world from PyQt', self)
        #title.setAlignment(Qt.AlignCenter)
        #l.addWidget(title, 0, 0)

    def encode_selection(self):
        print('ENCODE')
        timer = QTimer(self)
        timer.timeout.connect(self._on_timeout)
        timer.setInterval(200)
        timer.start()

    def _on_timeout(self):
        # update random model stuff
        model = self._model
        row = random.randrange(0, len(model._data))
        item = model._data[row]
        item = (
            item[0],
            item[1],
            min(1.0, item[2] + 0.1*random.random()))
        model._data[row] = item
        idx = model.index(row)
        model.dataChanged.emit(idx, idx)

        print('TIMEOUT')

    def delete_selection(self):
        sel = self._view.selectionModel()
        idxs = [QPersistentModelIndex(idx) for idx in sel.selectedIndexes()]
        for idx in idxs:
            self._model.removeRow(idx.row())
        idxs = None
        sel.clear()
        pass

    def init_listview(self):
        lw = QListWidget(self)
        self.setCentralWidget(lw)

        for entry in os.scandir('./thumbs'):
            icon = QIcon(entry.path)
            item = QListWidgetItem(icon, entry.name, lw)

    def init_listview2(self):
        view = QListView(self)
        self.setCentralWidget(view)

        #model = QStandardItemModel()
        model = MyListModel()
        model._data = []
        view.setModel(model)
        view.setSelectionMode(QListView.SelectionMode.ExtendedSelection)

        delegate = MyItemDelegate()
        view.setItemDelegate(delegate)

        # adding data to the table
        if 0:
            with open('media-items.pickle', 'rb') as f:
                media_items = list(pickle.load(f).values())

            def foo():
                try:
                    item = media_items.pop()
                    model._update_item(item)
                    QTimer.singleShot(random.randrange(50, 100), foo)
                except IndexError:
                    return

            QTimer.singleShot(300, foo)

        self._view = view
        self._model = model

    def import_media(self):
        #url = QFileDialog.getExistingDirectoryUrl(self, 'Import media')
        filenames, _ = QFileDialog.getOpenFileNames(
                self,
                'Import movies',
                filter='Movies (*.mov *.avi *.mp4 *.m4v *.webm)')
        print(filenames)

    def dragEnterEvent(self, e):
        print('dragEnter')
        e.accept()

    def dropEvent(self, e):
        print('drop')
        for url in e.mimeData().urls():
            if url.isLocalFile():
                print(url.toLocalFile())

        print(f'''
            mime-data: {e.mimeData().formats()}
            urls: {e.mimeData().urls()}
        ''')


if __name__ == '__main__':
    # create the app
    app = QApplication(sys.argv)

    # create my widgets
    main = HelloWindow()
    main.show()

    if 1:
        # timer
        engine = create_engine()

        main.statusBar().showMessage('Scanning...')
        engine.send({
            'command': 'scan_paths',
            'kwargs': {
                'paths': ['.'],
                'sequence_framerate': (30,1),
                }
            })

        def on_timeout():
            while True:
                msg = engine.poll()
                if not msg:
                    break
                if msg[0] == 'media_update':
                    id = msg[1]
                    data = msg[2]
                    data['id'] = id
                    print(msg[0], id, data.keys())
                    main._model._update_item(data)

                elif msg[0] == 'scan_complete':
                    print('SCAN_COMPLETE')
                    main.statusBar().showMessage('Scan complete')

        timer = QTimer()
        timer.timeout.connect(on_timeout)
        timer.setInterval(200)
        timer.start()

    # start the app
    rc = app.exec_()
    print('EXEC RETURNED, QUITTING')

    engine.join()
    sys.exit(rc)
