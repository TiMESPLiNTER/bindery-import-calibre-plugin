"""Integration tests for the calibre-facing parts of the plugin: metadata
mapping (dialog.SearchDialog._build_metadata) and the library-import call
(db.add_books) that dialog.SearchDialog.do_import() relies on.

These touch real calibre APIs (Qt, calibre.db, calibre.ebooks.metadata) that
only exist inside calibre's bundled Python, so they can't run under a plain
`python3 -m unittest`. Run them with calibre's own interpreter instead:

    calibre-customize -a bindery_import.zip   # plugin must be installed once
    calibre-debug tests/test_calibre_integration.py

A disposable calibre library is created under a temp directory for
LibraryImportTest and removed again afterwards; your real calibre library is
never touched. No network access is used -- FakeClient stands in for
BinderyClient.
"""
import os
import shutil
import sys
import tempfile
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qt.core import QApplication, QBuffer, QIODevice, QPixmap, Qt  # noqa: E402

from calibre.customize.ui import initialized_plugins  # noqa: E402

# Registers the calibre_plugins.bindery_import.* namespace; the plugin zip
# must already be installed (calibre-customize -a bindery_import.zip).
list(initialized_plugins())

from calibre.db.legacy import LibraryDatabase  # noqa: E402

# Imported through the same calibre_plugins.* namespace dialog.py itself uses
# (not the bare top-level "client" module) so that the except clause in
# dialog._build_metadata(), which catches calibre_plugins...client.BinderyError,
# actually matches the exception FakeClient raises below.
from calibre_plugins.bindery_import.client import BinderyError  # noqa: E402
from dialog import SearchDialog  # noqa: E402

app = QApplication.instance() or QApplication([])


def _make_tiny_jpeg():
    """A real, valid, tiny JPEG -- avoids the harmless but noisy
    "JPEG datastream contains no image" warnings a fake byte string
    would trigger in calibre's async cover/page-count workers."""
    pixmap = QPixmap(4, 4)
    pixmap.fill(Qt.GlobalColor.blue)
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buf, 'JPEG')
    return bytes(buf.data())


FAKE_COVER_BYTES = _make_tiny_jpeg()

BOOK_FIXTURE = {
    'id': 1,
    'title': 'Fetish - Fashion, Sex & Power',
    'description': 'A history of fetish fashion.',
    'genres': ['Fashion', 'History', 'Fashion'],  # duplicate on purpose
    'releaseDate': '1996-01-01T00:00:00Z',
    'language': 'en',
    'ratingsCount': 12,
    'averageRating': 4.5,
    'foreignBookId': 'OL891144W',
    'asin': '',
    'imageUrl': '/api/v1/images?url=https://covers.example/1.jpg',
    'author': {'authorName': 'Valerie Steele'},
}


class FakeClient:
    """Stands in for BinderyClient so tests never touch the network."""

    def __init__(self, cover=FAKE_COVER_BYTES, raise_on_cover=None):
        self.cover = cover
        self.raise_on_cover = raise_on_cover

    def download_cover(self, image_url):
        if self.raise_on_cover:
            raise self.raise_on_cover
        return self.cover


class BuildMetadataTest(unittest.TestCase):
    def setUp(self):
        self.dialog = SearchDialog.__new__(SearchDialog)

    def test_maps_all_known_fields(self):
        mi = self.dialog._build_metadata(BOOK_FIXTURE, FakeClient())

        self.assertEqual(mi.title, 'Fetish - Fashion, Sex & Power')
        self.assertEqual(mi.authors, ['Valerie Steele'])
        self.assertEqual(mi.comments, 'A history of fetish fashion.')
        self.assertEqual(mi.tags, ['Fashion', 'History'])  # deduped, order kept
        self.assertEqual(mi.pubdate.year, 1996)
        self.assertEqual(mi.languages, ['eng'])
        self.assertEqual(mi.rating, 9)  # 4.5 * 2, rounded
        self.assertEqual(mi.identifiers, {'bindery': '1', 'olid': 'OL891144W'})
        self.assertEqual(mi.cover_data, ('jpg', FAKE_COVER_BYTES))

    def test_skips_rating_when_no_ratings_count(self):
        book = dict(BOOK_FIXTURE, ratingsCount=0)
        mi = self.dialog._build_metadata(book, FakeClient())
        self.assertIsNone(mi.rating)

    def test_missing_author_falls_back_to_unknown(self):
        book = dict(BOOK_FIXTURE, author=None)
        mi = self.dialog._build_metadata(book, FakeClient())
        self.assertEqual(mi.authors, ['Unknown'])

    def test_cover_download_failure_does_not_raise(self):
        client = FakeClient(raise_on_cover=BinderyError('boom'))
        mi = self.dialog._build_metadata(BOOK_FIXTURE, client)
        self.assertIsNone(mi.cover_data[1])

    def test_asin_identifier_included_when_present(self):
        book = dict(BOOK_FIXTURE, asin='B00TEST123')
        mi = self.dialog._build_metadata(book, FakeClient())
        self.assertEqual(mi.identifiers, {'bindery': '1', 'olid': 'OL891144W', 'asin': 'B00TEST123'})

    def test_missing_release_date_leaves_pubdate_unset(self):
        book = dict(BOOK_FIXTURE, releaseDate=None)
        mi = self.dialog._build_metadata(book, FakeClient())
        self.assertFalse(mi.pubdate and mi.pubdate.year == 1996)

    def test_no_genres_leaves_tags_unset(self):
        book = dict(BOOK_FIXTURE, genres=[])
        mi = self.dialog._build_metadata(book, FakeClient())
        self.assertFalse(mi.tags)


class LibraryImportTest(unittest.TestCase):
    """Exercises the real db.add_books() call, the same one
    dialog.SearchDialog.do_import() uses, against a disposable library."""

    def setUp(self):
        self.library_path = tempfile.mkdtemp(prefix='bindery_import_test_')
        self.db = LibraryDatabase(self.library_path)
        self.book_file = tempfile.NamedTemporaryFile(suffix='.epub', delete=False)
        self.book_file.write(b'fake epub content')
        self.book_file.close()

    def tearDown(self):
        self.db.close()
        os.remove(self.book_file.name)
        shutil.rmtree(self.library_path, ignore_errors=True)

    def test_add_books_keeps_gui_view_in_sync(self):
        dialog = SearchDialog.__new__(SearchDialog)
        mi = dialog._build_metadata(BOOK_FIXTURE, FakeClient())

        before = len(self.db.data)
        _, ids = self.db.add_books(
            [self.book_file.name], ['EPUB'], [mi], add_duplicates=True, return_ids=True,
        )
        after = len(self.db.data)

        self.assertEqual(len(ids), 1)
        self.assertEqual(after, before + 1)
        book_id = ids[0]
        self.assertEqual(self.db.new_api.formats(book_id), ('EPUB',))
        self.assertTrue(self.db.new_api.field_for('cover', book_id))
        self.assertEqual(self.db.new_api.field_for('title', book_id), BOOK_FIXTURE['title'])


class FakeGui:
    """Stands in for calibre's main GUI object; SearchDialog only ever
    touches gui.current_db."""

    def __init__(self, db):
        self.current_db = db


class AlreadyInLibraryTest(unittest.TestCase):
    """Exercises _bindery_ids_already_in_library(), which drives the
    grey-out/unselectable treatment for search results already imported."""

    def setUp(self):
        self.library_path = tempfile.mkdtemp(prefix='bindery_import_test_')
        self.db = LibraryDatabase(self.library_path)
        self.dialog = SearchDialog.__new__(SearchDialog)
        self.dialog.gui = FakeGui(self.db)

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.library_path, ignore_errors=True)

    def test_empty_library_has_no_bindery_ids(self):
        self.assertEqual(self.dialog._bindery_ids_already_in_library(), set())

    def test_finds_book_with_bindery_identifier(self):
        mi = self.dialog._build_metadata(BOOK_FIXTURE, FakeClient())
        self.db.new_api.create_book_entry(mi, add_duplicates=True)

        self.assertEqual(self.dialog._bindery_ids_already_in_library(), {'1'})

    def test_ignores_books_without_bindery_identifier(self):
        from calibre.ebooks.metadata.book.base import Metadata

        self.db.new_api.create_book_entry(Metadata('Some other book', ['Someone']), add_duplicates=True)

        self.assertEqual(self.dialog._bindery_ids_already_in_library(), set())


def _run():
    # calibre-debug does not execute this file as the '__main__' module, so
    # unittest.main()'s default discovery (which looks at sys.modules['__main__'])
    # finds nothing. Build the suite explicitly from the classes above instead.
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(BuildMetadataTest))
    suite.addTests(loader.loadTestsFromTestCase(LibraryImportTest))
    suite.addTests(loader.loadTestsFromTestCase(AlreadyInLibraryTest))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


_run()
