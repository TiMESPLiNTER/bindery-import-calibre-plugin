# Bindery Import

A [calibre](https://calibre-ebook.com/) plugin that connects to a Bindery
server, lets you search its book catalog, and imports selected books straight
into your local calibre library — cover, description, tags, publish date,
language, rating and identifiers included.

## Features

- Toolbar action opens a search dialog for your Bindery server
- Search by title/author, filter to "Imported only" (books Bindery actually
  has a file for) or "All"
- Cover thumbnails in the results list, fetched in the background
- `wanted` books (no file available yet) are shown in yellow and are not
  selectable; `imported` books are shown in green
- Books you've already imported are detected (via the `bindery` identifier,
  see below) and shown greyed out / not selectable, so you can't accidentally
  import duplicates
- Imports selected books into your calibre library with:
  - the book file (whatever format Bindery has — epub, mobi, azw3, ...)
  - cover image
  - title, author(s)
  - description → comments
  - genres → tags
  - release date → pubdate
  - language
  - rating (when Bindery has one)
  - identifiers: the Bindery book id (`bindery`, used to detect
    already-imported books), OpenLibrary work id (`olid`) and ASIN when
    available
- Authenticates with Bindery via API key (`X-Api-Key` header) — no
  session/cookie handling needed

## Requirements

- calibre >= 5.0
- A running Bindery instance and an API key for it (Bindery → Settings →
  find/generate an API key for external integrations)

## Installation

1. Build the plugin zip:

   ```sh
   zip -r bindery_import.zip __init__.py action.py config.py client.py dialog.py \
       plugin-import-name-bindery_import.txt images
   ```

2. Install it into calibre:

   ```sh
   calibre-customize -a bindery_import.zip
   ```

   Or, from calibre's GUI: *Preferences → Plugins → Load plugin from file*.

3. Restart calibre.

## Configuration

*Preferences → Plugins → Bindery Import* (or the plugin's customize button in
the plugin list) and set:

- **Bindery URL** — e.g. `http://bindery.local:8787`
- **API key**

The API key is stored in calibre's plugin config
(`~/.config/calibre/plugins/bindery_import.json` on Linux, the equivalent
calibre config directory on macOS/Windows) in plaintext, same as calibre
stores other plugin credentials. Treat that file accordingly.

## Usage

Click the "Bindery Import" toolbar button, search, select one or more
`imported` rows, and click **Import selected**. A summary dialog reports how
many books were imported, skipped (no file on Bindery yet), or failed.

## Limitations

- Bindery's book API doesn't expose series, publisher or ISBN, so those
  aren't imported (there's nothing to map).
- No narrator field — calibre has no built-in narrator field for audiobooks;
  would require a custom column.
- Only books with `status: imported` on Bindery have a file to download;
  `wanted` books are metadata-only on the Bindery side.

## Development

The plugin is plain Python + Qt (via calibre's `qt.core` shim) and calibre's
own APIs (`calibre.db`, `calibre.ebooks.metadata`, ...). Those calibre/Qt
modules only exist inside calibre's bundled Python interpreter, not a regular
`pip`-installed environment.

### Running the tests

`tests/test_client.py` covers `BinderyClient` in isolation (HTTP mocked via
`unittest.mock`, no calibre dependency):

```sh
python3 -m unittest discover -s tests -p 'test_client.py' -v
```

`tests/test_calibre_integration.py` covers the calibre-facing parts —
metadata mapping and the `db.add_books()` call used to import a book — against
a disposable, throwaway calibre library (your real library is never touched)
and a fake Bindery client (no network access). It needs calibre's own
interpreter and the plugin installed once:

```sh
calibre-customize -a bindery_import.zip
calibre-debug tests/test_calibre_integration.py
```

## License

[MIT](LICENSE)
