"""Unit tests for BinderyClient.

Pure stdlib, no network access and no calibre installation required.

Run with:
    python3 -m unittest discover -s tests
"""
import json
import os
import sys
import unittest
from io import BytesIO
from unittest import mock
from urllib.error import HTTPError, URLError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from client import BinderyAuthError, BinderyClient, BinderyError  # noqa: E402


class FakeResponse(BytesIO):
    def __init__(self, data, headers=None):
        super().__init__(data)
        self.headers = headers or {}


class BinderyClientTest(unittest.TestCase):
    def setUp(self):
        self.client = BinderyClient('http://example.test:8787', 'secret-key')

    def test_base_url_trailing_slash_is_stripped(self):
        c = BinderyClient('http://example.test:8787/', 'key')
        self.assertEqual(c.base_url, 'http://example.test:8787')

    @mock.patch('urllib.request.urlopen')
    def test_search_books_sends_api_key_header_and_parses_json(self, mock_urlopen):
        payload = {'items': [{'id': 1, 'title': 'Foo'}], 'total': 1, 'limit': 100, 'offset': 0}
        mock_urlopen.return_value = FakeResponse(json.dumps(payload).encode('utf-8'))

        result = self.client.search_books(query='foo', status='imported', limit=10, offset=5)

        self.assertEqual(result, payload)
        request = mock_urlopen.call_args[0][0]
        self.assertEqual(request.get_header('X-api-key'), 'secret-key')
        self.assertIn('search=foo', request.full_url)
        self.assertIn('status=imported', request.full_url)
        self.assertIn('limit=10', request.full_url)
        self.assertIn('offset=5', request.full_url)

    @mock.patch('urllib.request.urlopen')
    def test_search_books_omits_search_and_status_when_not_given(self, mock_urlopen):
        payload = {'items': [], 'total': 0, 'limit': 100, 'offset': 0}
        mock_urlopen.return_value = FakeResponse(json.dumps(payload).encode('utf-8'))

        self.client.search_books()

        request = mock_urlopen.call_args[0][0]
        self.assertNotIn('search=', request.full_url)
        self.assertNotIn('status=', request.full_url)

    @mock.patch('urllib.request.urlopen')
    def test_download_book_file_parses_rfc5987_filename(self, mock_urlopen):
        headers = {
            'Content-Disposition': (
                'attachment; filename="x.epub"; '
                "filename*=UTF-8''Fetish%20%26%20Power.epub"
            )
        }
        mock_urlopen.return_value = FakeResponse(b'epub-bytes', headers=headers)

        filename, data = self.client.download_book_file(42)

        self.assertEqual(filename, 'Fetish & Power.epub')
        self.assertEqual(data, b'epub-bytes')
        request = mock_urlopen.call_args[0][0]
        self.assertTrue(request.full_url.endswith('/api/v1/book/42/file'))

    @mock.patch('urllib.request.urlopen')
    def test_download_book_file_falls_back_to_plain_filename(self, mock_urlopen):
        headers = {'Content-Disposition': 'attachment; filename="simple.mobi"'}
        mock_urlopen.return_value = FakeResponse(b'mobi-bytes', headers=headers)

        filename, _ = self.client.download_book_file(1)

        self.assertEqual(filename, 'simple.mobi')

    @mock.patch('urllib.request.urlopen')
    def test_download_book_file_handles_missing_disposition(self, mock_urlopen):
        mock_urlopen.return_value = FakeResponse(b'bytes')

        filename, data = self.client.download_book_file(1)

        self.assertIsNone(filename)
        self.assertEqual(data, b'bytes')

    @mock.patch('urllib.request.urlopen')
    def test_download_cover_returns_raw_bytes(self, mock_urlopen):
        mock_urlopen.return_value = FakeResponse(b'\xff\xd8jpeg-bytes')

        data = self.client.download_cover('/api/v1/images?url=x')

        self.assertEqual(data, b'\xff\xd8jpeg-bytes')

    @mock.patch('urllib.request.urlopen')
    def test_401_raises_bindery_auth_error(self, mock_urlopen):
        mock_urlopen.side_effect = HTTPError('url', 401, 'Unauthorized', {}, None)

        with self.assertRaises(BinderyAuthError):
            self.client.search_books()

    @mock.patch('urllib.request.urlopen')
    def test_other_http_error_raises_bindery_error(self, mock_urlopen):
        mock_urlopen.side_effect = HTTPError('url', 500, 'Server Error', {}, None)

        with self.assertRaises(BinderyError):
            self.client.search_books()

    @mock.patch('urllib.request.urlopen')
    def test_connection_error_raises_bindery_error(self, mock_urlopen):
        mock_urlopen.side_effect = URLError('Connection refused')

        with self.assertRaises(BinderyError):
            self.client.search_books()


if __name__ == '__main__':
    unittest.main()
