import json
import re
import urllib.error
import urllib.parse
import urllib.request


class BinderyError(Exception):
    pass


class BinderyAuthError(BinderyError):
    pass


class BinderyClient:
    def __init__(self, base_url, api_key, timeout=30):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout

    def _request(self, method, path):
        url = self.base_url + path
        headers = {
            'Accept': 'application/json',
            'X-Api-Key': self.api_key,
            'User-Agent': 'calibre-bindery-import-plugin',
        }
        req = urllib.request.Request(url, headers=headers, method=method)
        try:
            return urllib.request.urlopen(req, timeout=self.timeout)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise BinderyAuthError('Bindery rejected the API key (401 Unauthorized)')
            raise BinderyError(f'Bindery returned HTTP {e.code} for {path}')
        except urllib.error.URLError as e:
            raise BinderyError(f'Could not reach Bindery at {self.base_url}: {e.reason}')

    def search_books(self, query='', status=None, limit=100, offset=0):
        params = {'limit': limit, 'offset': offset, 'sort': 'title-az'}
        if query:
            params['search'] = query
        if status:
            params['status'] = status
        qs = urllib.parse.urlencode(params)
        resp = self._request('GET', f'/api/v1/book?{qs}')
        return json.loads(resp.read().decode('utf-8'))

    def download_book_file(self, book_id):
        resp = self._request('GET', f'/api/v1/book/{book_id}/file')
        disposition = resp.headers.get('Content-Disposition', '')
        filename = None
        m = re.search(r"filename\*=UTF-8''([^;]+)", disposition)
        if m:
            filename = urllib.parse.unquote(m.group(1))
        else:
            m = re.search(r'filename="?([^";]+)"?', disposition)
            if m:
                filename = m.group(1)
        return filename, resp.read()

    def download_cover(self, image_url):
        """image_url is the (server-relative) 'imageUrl' field from a book record."""
        resp = self._request('GET', image_url)
        return resp.read()
