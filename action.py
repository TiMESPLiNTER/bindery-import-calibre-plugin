from calibre.gui2.actions import InterfaceAction


class BinderyImportAction(InterfaceAction):
    name = 'Bindery Import'
    action_spec = ('Bindery Import', None, 'Search Bindery and import books', None)
    action_type = 'current'

    def genesis(self):
        self.qaction.setIcon(get_icons('images/icon.png'))
        self.qaction.triggered.connect(self.show_dialog)

    def show_dialog(self):
        from calibre_plugins.bindery_import.dialog import SearchDialog
        d = SearchDialog(self.gui)
        d.exec()
