from PyQt5.QtWidgets import (
        qApp, QListView,
        QStyledItemDelegate, QStyle, QStyleOptionProgressBar,
        )
from PyQt5.QtGui import (
        QImage, QFont, QBrush,
        QTextDocument,
        )
from PyQt5.QtCore import (
        Qt, QAbstractListModel,
        QSize, QRect,
        QModelIndex,
        )

from utils import format_size
from config import config

class MediaListView(QListView):
    def __init__(self, parent=None):
        QListView.__init__(self, parent)
        delegate = MediaItemDelegate()
        self.setItemDelegate(delegate)
        self.setSelectionMode(QListView.SelectionMode.ExtendedSelection)


class MediaListModel(QAbstractListModel):
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

    def get_media_id_for_index(self, idx):
        row = idx.row()
        item = self._items[row]
        return item['id']

    def _remove_item_by_id(self, id):
        row = self._find_row_with_id(id)
        self.removeRow(row)

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
        item['_html'] = format_media_item_html(item)

        if '_image' not in item:
            image_data = item.get('thumbnail')
            if image_data:
                image = QImage()
                image.loadFromData(image_data)
                item['_image'] = image

        # FIXME
        item['_progress'] = item.get('progress', 0.0)

        if row < 0:
            row = len(self._items)
            self.beginInsertRows(QModelIndex(), row, row)
            self._items.append(item)
            self.endInsertRows()
        else:
            index = self.index(row)
            self.dataChanged.emit(index, index, [])


class MediaItemDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        QStyledItemDelegate.__init__(self, parent)

    def paint(self, painter, option, index):
        item = index.data()

        painter.save()

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

state_colors = {
    'new': 'gray',
    'ready': 'gray',
    'done': 'green',
    'error': 'red',
    'encoding': 'blue',
    'queued': 'orange',
    }

def format_media_item_html(item):
    displayname = item.get('displayname')
    codec = item.get('codec')
    pixfmt = item.get('pixfmt')
    resolution = item.get('resolution')
    duration = item.get('duration')
    filesize = item.get('filesize')
    state = item.get('state')

    html = []
    if displayname:
        html.append(f'<b>{displayname}</b>')

    deets = []

    if config['ui'].get('details_style') == 'short':
        if resolution:
            deets.append(f'{resolution[0]}x{resolution[1]}')
        if codec and pixfmt:
            colorspace = item.get('colorspace')
            if colorspace:
                colorspace = f', {colorspace}'
            else:
                colorspace = ''
            deets.append(f'{codec} ({pixfmt}{colorspace})')
        if duration:
            deets.append(f'{duration:.02f}s')
        deets = [' '.join(deets)]

        if filesize:
            deets.append(f'{format_size(filesize)}')

        if state and state != 'ready':
            color = state_colors.get(state, 'auto')
            deets.append(f'<b style="color: {color};">{state.upper()}</b>')
    else:
        if codec and pixfmt:
            deets.append(f'Codec: {codec} ({pixfmt})')
        if resolution:
            deets.append(f'Resolution: {resolution[0]}x{resolution[1]}')
        if duration:
            deets.append(f'Duration: {duration:.02f}s')
        if filesize:
            deets.append(f'Size: {format_size(filesize)}')
        if state:
            deets.append(f'State: {state}')

    if deets:
        deets = '<br>'.join(deets)
        html.append(f'<div style="font-style: normal; color: gray;">{deets}</div>')

    return ''.join(html)
