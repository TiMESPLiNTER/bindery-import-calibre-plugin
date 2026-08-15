import os
import tempfile

from qt.core import (
    QAbstractItemView,
    QColor,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QIcon,
    QLabel,
    QLineEdit,
    QPixmap,
    QPushButton,
    QSize,
    Qt,
    QTableWidget,
    QTableWidgetItem,
    QThread,
    QVBoxLayout,
    pyqtSignal,
)

from calibre.ebooks.metadata.book.base import Metadata
from calibre.gui2 import error_dialog, info_dialog
from calibre.utils.date import parse_date
from calibre.utils.localization import canonicalize_lang

from calibre_plugins.bindery_import.client import BinderyAuthError, BinderyClient, BinderyError
from calibre_plugins.bindery_import.config import prefs


COVER_ICON_SIZE = QSize(32, 44)

STATUS_COLORS = {
    'imported': (QColor('#d9f2df'), QColor('#1e6b34')),  # light green bg, dark green text
    'wanted': (QColor('#fff6cf'), QColor('#8a6d00')),  # light yellow bg, dark yellow text
}
IN_LIBRARY_COLORS = (QColor('#e6e6e6'), QColor('#5a5a5a'))  # grey bg, grey text

# Identifier type used to tag imported books with their Bindery book id, so
# we can tell which local books came from Bindery and cross-check search
# results against what's already in the library.
BINDERY_IDENTIFIER_KEY = 'bindery'


class CoverFetchThread(QThread):
    """Downloads cover thumbnails for search results in the background so the
    UI stays responsive."""

    cover_ready = pyqtSignal(int, bytes)

    def __init__(self, client, rows_and_urls):
        super().__init__()
        self.client = client
        self.rows_and_urls = rows_and_urls
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        for row, image_url in self.rows_and_urls:
            if self._stop:
                return
            try:
                data = self.client.download_cover(image_url)
            except (BinderyAuthError, BinderyError):
                continue
            if self._stop:
                return
            self.cover_ready.emit(row, data)


class SearchDialog(QDialog):
    def __init__(self, gui):
        super().__init__(gui)
        self.gui = gui
        self.setWindowTitle('Bindery Import')
        self.resize(700, 500)
        self.results = []
        self.cover_thread = None

        layout = QVBoxLayout(self)

        search_row = QHBoxLayout()
        self.query_edit = QLineEdit()
        self.query_edit.setPlaceholderText('Search title, author...')
        self.query_edit.returnPressed.connect(self.do_search)
        search_row.addWidget(self.query_edit)

        self.status_filter = QComboBox()
        self.status_filter.addItem('Imported only', 'imported')
        self.status_filter.addItem('All', '')
        search_row.addWidget(self.status_filter)

        search_btn = QPushButton('Search')
        search_btn.clicked.connect(self.do_search)
        search_row.addWidget(search_btn)
        layout.addLayout(search_row)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(['Cover', 'Title', 'Author', 'Status', 'Format'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setIconSize(COVER_ICON_SIZE)
        self.table.verticalHeader().setDefaultSectionSize(COVER_ICON_SIZE.height() + 4)
        self.table.setColumnWidth(0, COVER_ICON_SIZE.width() + 12)
        self.table.setColumnWidth(1, 320)
        self.table.setColumnWidth(2, 180)
        layout.addWidget(self.table)

        self.status_label = QLabel('')
        layout.addWidget(self.status_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        import_btn = QPushButton('Import selected')
        import_btn.clicked.connect(self.do_import)
        btn_row.addWidget(import_btn)
        close_btn = QPushButton('Close')
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _get_client(self):
        url = prefs['url']
        api_key = prefs['api_key']
        if not url or not api_key:
            error_dialog(
                self,
                'Bindery Import',
                'Configure the Bindery URL and API key in '
                'Preferences -> Plugins -> Bindery Import first.',
                show=True,
            )
            return None
        return BinderyClient(url, api_key)

    def _bindery_ids_already_in_library(self):
        """Book ids (as strings) of every book already in the local calibre
        library that carries our 'bindery' identifier."""
        db = self.gui.current_db
        existing = set()
        for book_id in db.new_api.all_book_ids():
            identifiers = db.new_api.field_for('identifiers', book_id) or {}
            bindery_id = identifiers.get(BINDERY_IDENTIFIER_KEY)
            if bindery_id:
                existing.add(bindery_id)
        return existing

    def do_search(self):
        client = self._get_client()
        if client is None:
            return
        self._stop_cover_thread()
        query = self.query_edit.text().strip()
        status = self.status_filter.currentData()
        self.status_label.setText('Searching...')
        try:
            data = client.search_books(query=query, status=status, limit=100)
        except (BinderyAuthError, BinderyError) as e:
            self.status_label.setText('')
            error_dialog(self, 'Bindery Import', str(e), show=True)
            return

        already_in_library = self._bindery_ids_already_in_library()

        self.results = data.get('items', [])
        self.table.setRowCount(len(self.results))
        cover_jobs = []
        for row, book in enumerate(self.results):
            title = book.get('title', '')
            author = (book.get('author') or {}).get('authorName', '')
            status_val = book.get('status', '')
            in_library = str(book.get('id')) in already_in_library
            fmt = self._format_for(book)
            self.table.setItem(row, 0, QTableWidgetItem())
            self.table.setItem(row, 1, QTableWidgetItem(title))
            self.table.setItem(row, 2, QTableWidgetItem(author))
            status_text = f'{status_val} (in library)' if in_library else status_val
            status_item = QTableWidgetItem(status_text)
            colors = IN_LIBRARY_COLORS if in_library else STATUS_COLORS.get(status_val)
            if colors:
                bg, fg = colors
                status_item.setBackground(bg)
                status_item.setForeground(fg)
            self.table.setItem(row, 3, status_item)
            self.table.setItem(row, 4, QTableWidgetItem(fmt))
            if status_val == 'wanted' or in_library:
                for col in range(self.table.columnCount()):
                    item = self.table.item(row, col)
                    # Stripping only ItemIsSelectable still lets the row become
                    # the "current" index on click (a focus rectangle that looks
                    # like a selection); also stripping ItemIsEnabled blocks
                    # that entirely.
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable & ~Qt.ItemFlag.ItemIsEnabled)
            if book.get('imageUrl'):
                cover_jobs.append((row, book['imageUrl']))
        self.status_label.setText(f'{data.get("total", len(self.results))} result(s)')

        if cover_jobs:
            self.cover_thread = CoverFetchThread(client, cover_jobs)
            self.cover_thread.cover_ready.connect(self._on_cover_ready)
            self.cover_thread.start()

    def _on_cover_ready(self, row, data):
        if row >= self.table.rowCount():
            return
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            return
        pixmap = pixmap.scaled(
            COVER_ICON_SIZE, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        item = self.table.item(row, 0)
        if item is not None:
            item.setIcon(QIcon(pixmap))

    def _stop_cover_thread(self):
        if self.cover_thread is not None:
            self.cover_thread.cover_ready.disconnect(self._on_cover_ready)
            self.cover_thread.stop()
            self.cover_thread.wait()
            self.cover_thread = None

    def reject(self):
        self._stop_cover_thread()
        super().reject()

    def _format_for(self, book):
        if book.get('mediaType') == 'audiobook':
            path = book.get('audiobookFilePath') or ''
        else:
            path = book.get('ebookFilePath') or book.get('filePath') or ''
        ext = os.path.splitext(path)[1].lstrip('.')
        return ext or ''

    def _build_metadata(self, book, client):
        author_name = (book.get('author') or {}).get('authorName', '')
        mi = Metadata(book.get('title', 'Unknown'), [author_name] if author_name else ['Unknown'])

        if book.get('description'):
            mi.comments = book['description']

        if book.get('genres'):
            mi.tags = list(dict.fromkeys(book['genres']))

        if book.get('releaseDate'):
            try:
                mi.pubdate = parse_date(book['releaseDate'])
            except Exception:
                pass

        lang = canonicalize_lang(book.get('language'))
        if lang:
            mi.languages = [lang]

        if book.get('ratingsCount'):
            mi.rating = max(0, min(10, round((book.get('averageRating') or 0) * 2)))

        identifiers = {BINDERY_IDENTIFIER_KEY: str(book['id'])}
        if book.get('foreignBookId'):
            identifiers['olid'] = book['foreignBookId']
        if book.get('asin'):
            identifiers['asin'] = book['asin']
        mi.set_identifiers(identifiers)

        image_url = book.get('imageUrl')
        if image_url:
            try:
                mi.cover_data = ('jpg', client.download_cover(image_url))
            except (BinderyAuthError, BinderyError):
                pass  # missing cover shouldn't block the import

        return mi

    def do_import(self):
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()})
        if not rows:
            error_dialog(self, 'Bindery Import', 'Select at least one book to import.', show=True)
            return
        client = self._get_client()
        if client is None:
            return

        db = self.gui.current_db
        skipped, failed = 0, []
        paths, formats, metadatas = [], [], []

        for row in rows:
            book = self.results[row]
            if book.get('status') != 'imported':
                skipped += 1
                continue
            try:
                filename, data = client.download_book_file(book['id'])
            except (BinderyAuthError, BinderyError) as e:
                failed.append((book.get('title', '?'), str(e)))
                continue

            ext = (os.path.splitext(filename or '')[1].lstrip('.') or 'epub').lower()
            with tempfile.NamedTemporaryFile(suffix='.' + ext, delete=False) as tmp:
                tmp.write(data)
                paths.append(tmp.name)
            formats.append(ext.upper())
            metadatas.append(self._build_metadata(book, client))

        imported = 0
        try:
            if paths:
                # db.add_books() is the legacy API that keeps the GUI's book
                # list (db.data) in sync; using db.new_api.create_book_entry()
                # directly writes to the database but leaves the visible
                # library view unaware of the new rows.
                _, ids = db.add_books(paths, formats, metadatas, add_duplicates=True, return_ids=True)
                imported = len(ids)
        finally:
            for p in paths:
                os.remove(p)

        if imported:
            self.gui.library_view.model().books_added(imported)
            self.gui.tags_view.recount()

        msg = f'Imported {imported} book(s).'
        if skipped:
            msg += f' Skipped {skipped} (no file available on Bindery).'
        if failed:
            msg += f' Failed {len(failed)}: ' + '; '.join(t for t, _ in failed)
        info_dialog(self, 'Bindery Import', msg, show=True)
