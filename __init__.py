from calibre.customize import InterfaceActionBase


class BinderyImportPlugin(InterfaceActionBase):
    name = 'Bindery Import'
    description = 'Search a Bindery server and import books into your Calibre library'
    supported_platforms = ['windows', 'osx', 'linux']
    author = 'timesplinter'
    version = (1, 0, 0)
    minimum_calibre_version = (5, 0, 0)
    actual_plugin = 'calibre_plugins.bindery_import.action:BinderyImportAction'

    def is_customizable(self):
        return True

    def config_widget(self):
        from calibre_plugins.bindery_import.config import ConfigWidget
        return ConfigWidget()

    def save_settings(self, config_widget):
        config_widget.save_settings()
