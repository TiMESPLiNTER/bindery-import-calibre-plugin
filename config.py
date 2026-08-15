from qt.core import QFormLayout, QLineEdit, QWidget

from calibre.utils.config import JSONConfig

prefs = JSONConfig('plugins/bindery_import')
prefs.defaults['url'] = ''
prefs.defaults['api_key'] = ''


class ConfigWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QFormLayout(self)

        self.url_edit = QLineEdit(prefs['url'])
        self.url_edit.setPlaceholderText('http://bindery.local:8787')
        layout.addRow('Bindery URL:', self.url_edit)

        self.api_key_edit = QLineEdit(prefs['api_key'])
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addRow('API key:', self.api_key_edit)

    def save_settings(self):
        prefs['url'] = self.url_edit.text().strip().rstrip('/')
        prefs['api_key'] = self.api_key_edit.text().strip()
