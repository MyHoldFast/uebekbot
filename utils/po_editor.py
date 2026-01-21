import sys
import asyncio
import subprocess
import shutil
from pathlib import Path
import aiohttp
import polib
import markdown
import json

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTableWidget, QTableWidgetItem,
    QPushButton, QVBoxLayout, QWidget, QHBoxLayout,
    QMessageBox, QDialog, QLabel, QPlainTextEdit,
    QMenu, QInputDialog, QProgressDialog, QTextBrowser
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QDesktopServices

CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parent.parent
LOCALES_PATH = PROJECT_ROOT / "locales"

DOMAIN = "messages"
BASE_LANG = "ru"


async def translate_text(session, text, source_lang, target_lang):
    if not text.strip():
        return ""
    url = "https://translate.googleapis.com/translate_a/single"
    params = {
        "client": "gtx",
        "sl": source_lang,
        "tl": target_lang,
        "dt": "t",
        "q": text
    }
    try:
        async with session.post(url, data=params) as response:
            content_type = response.headers.get('Content-Type', '')
            if 'application/json' not in content_type and 'text/javascript' not in content_type:
                text_response = await response.text()
                if "sorry/index" in str(response.url):
                    error_url = str(response.url)
                    return {"error": "captcha", "url": error_url}
                return {"error": "content_type", "text": text_response}
            
            data = await response.json()
            if data and data[0]:
                return "".join(p[0] for p in data[0])
            return ""
    except aiohttp.ClientError as e:
        return {"error": "client_error", "message": str(e)}
    except json.JSONDecodeError as e:
        return {"error": "json_decode", "message": str(e)}


def show_po_text(text):
    return text.replace("\n", "\\n")


def save_po_text(text):
    return text.replace("\\n", "\n")


class POManager:
    def __init__(self):
        self.locales = self._discover_locales()
        self.pos = self._load_pos()

    def _discover_locales(self):
        if not LOCALES_PATH.exists():
            return [BASE_LANG]
        langs = sorted(p.name for p in LOCALES_PATH.iterdir() if p.is_dir())
        if BASE_LANG in langs:
            langs.remove(BASE_LANG)
        return [BASE_LANG] + langs

    def _po_path(self, lang):
        return LOCALES_PATH / lang / "LC_MESSAGES" / f"{DOMAIN}.po"

    def _load_pos(self):
        pos = {}
        for lang in self.locales:
            path = self._po_path(lang)
            path.parent.mkdir(parents=True, exist_ok=True)
            pos[lang] = polib.pofile(str(path), encoding="utf-8") if path.exists() else polib.POFile()
        return pos

    def add_language(self, lang):
        if lang in self.locales:
            return False
        self.locales.append(lang)
        path = self._po_path(lang)
        path.parent.mkdir(parents=True, exist_ok=True)
        po = polib.POFile()
        po.save(str(path))
        self.pos[lang] = po
        return True

    def delete_language(self, lang):
        if lang == BASE_LANG:
            return False
        if lang in self.locales:
            self.locales.remove(lang)
            self.pos.pop(lang, None)
            lang_dir = LOCALES_PATH / lang
            if lang_dir.exists():
                shutil.rmtree(lang_dir)
        return True

    def build_table(self):
        table = {}
        for lang, po in self.pos.items():
            for entry in po:
                table.setdefault(entry.msgid, {})
                table[entry.msgid][lang] = entry.msgstr
        return table

    def update(self, msgid, lang, text):
        po = self.pos[lang]
        entry = po.find(msgid)
        if entry:
            entry.msgstr = text
        else:
            po.append(polib.POEntry(msgid=msgid, msgstr=text))

    def rename_msgid(self, old, new):
        for po in self.pos.values():
            entry = po.find(old)
            if entry:
                entry.msgid = new

    def delete_msgid(self, msgid):
        for po in self.pos.values():
            entry = po.find(msgid)
            if entry:
                po.remove(entry)

    def msgid_exists(self, msgid):
        for po in self.pos.values():
            entry = po.find(msgid)
            if entry:
                return True
        return False

    def save_all(self):
        for po in self.pos.values():
            po.save()

    def compile(self):
        subprocess.run(["pybabel", "compile", "-d", str(LOCALES_PATH)])


class MultilineInputDialog(QDialog):
    def __init__(self, title, label, text="", parent=None, with_translate=False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(900, 550)
        self.text_edit = QPlainTextEdit(text)
        self.preview = QTextBrowser()
        self.preview.setVisible(False)
        self.translate_others = False
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(label))
        layout.addWidget(self.text_edit)
        layout.addWidget(self.preview)
        buttons = QHBoxLayout()
        self.preview_btn = QPushButton("👁 Preview Markdown")
        self.preview_btn.setCheckable(True)
        self.preview_btn.clicked.connect(self.toggle_preview)
        ok = QPushButton("OK")
        cancel = QPushButton("Cancel")
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(self.preview_btn)
        buttons.addStretch()
        buttons.addWidget(ok)
        if with_translate:
            self.save_translate_btn = QPushButton("💫 Save && Translate Others")
            self.save_translate_btn.clicked.connect(self.on_save_translate_clicked)
            buttons.addWidget(self.save_translate_btn)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)

    def toggle_preview(self):
        if self.preview_btn.isChecked():
            md_text = self.text_edit.toPlainText()
            html = markdown.markdown(md_text, extensions=["fenced_code", "tables", "nl2br"])
            self.preview.setHtml(html)
            self.preview.setVisible(True)
            self.text_edit.setVisible(False)
            self.preview_btn.setText("✏ Back to editor")
        else:
            self.preview.setVisible(False)
            self.text_edit.setVisible(True)
            self.preview_btn.setText("👁 Preview Markdown")

    def get_text(self):
        return self.text_edit.toPlainText()

    def on_save_translate_clicked(self):
        self.translate_others = True
        self.accept()


class POEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PO Editor")
        self.resize(1400, 750)
        self.manager = POManager()
        self.table = QTableWidget()
        self._original_msgids = {}
        self._init_ui()
        self._load_table()
        self.table.itemChanged.connect(self.on_item_changed)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_cell_context_menu)
        header = self.table.horizontalHeader()
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self.show_header_context_menu)

    def _init_ui(self):
        add_key = QPushButton("➕ Add key")
        add_lang = QPushButton("🌍 Add language")
        save = QPushButton("💾 Save")
        compile_btn = QPushButton("⚙ Compile")
        add_key.clicked.connect(self.add_key)
        add_lang.clicked.connect(self.add_language)
        save.clicked.connect(self.save)
        compile_btn.clicked.connect(self.compile)
        bar = QHBoxLayout()
        bar.addWidget(add_key)
        bar.addWidget(add_lang)
        bar.addWidget(save)
        bar.addWidget(compile_btn)
        bar.addStretch()
        layout = QVBoxLayout()
        layout.addLayout(bar)
        layout.addWidget(self.table)
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def _load_table(self):
        data = self.manager.build_table()
        locales = self.manager.locales
        self.table.setColumnCount(len(locales) + 1)
        self.table.setHorizontalHeaderLabels(["msgid"] + locales)
        self.table.setRowCount(len(data))
        
        for row, (msgid, langs) in enumerate(sorted(data.items())):
            self.table.setItem(row, 0, QTableWidgetItem(msgid))
            self._original_msgids[row] = msgid
            for col, lang in enumerate(locales, start=1):
                self.table.setItem(row, col, QTableWidgetItem(show_po_text(langs.get(lang, ""))))

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(100, self._adjust_columns_on_start)

    def _adjust_columns_on_start(self):
        self.table.resizeColumnToContents(0)
        self._adjust_lang_columns_width()

    def _msgid_exists_in_table(self, msgid):
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.text() == msgid:
                return True
        return False

    def _check_msgid_exists(self, msgid, exclude_row=None):
        if self.manager.msgid_exists(msgid):
            return True
            
        for row in range(self.table.rowCount()):
            if exclude_row is not None and row == exclude_row:
                continue
            item = self.table.item(row, 0)
            if item and item.text() == msgid:
                return True
        return False

    def add_language(self):
        lang, ok = QInputDialog.getText(self, "Add language", "Language code:")
        lang = lang.strip()
        if not ok or not lang or not self.manager.add_language(lang):
            return
        col = self.table.columnCount()
        self.table.insertColumn(col)
        self.table.setHorizontalHeaderItem(col, QTableWidgetItem(lang))
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._translate_new_language(lang))
        loop.close()
        self._adjust_lang_columns_width()

    async def _translate_new_language(self, lang):
        ru_col = 1
        texts = [save_po_text(self.table.item(r, ru_col).text()) for r in range(self.table.rowCount())]
        progress = QProgressDialog("Translating rows...", "Cancel", 0, len(texts), self)
        progress.setWindowTitle(f"Adding language: {lang}")
        progress.setMinimumDuration(0)
        progress.show()
        QApplication.processEvents()
        async with aiohttp.ClientSession() as session:
            for i, text in enumerate(texts):
                if progress.wasCanceled():
                    break
                result = await translate_text(session, text, BASE_LANG, lang)
                if isinstance(result, dict):
                    if result.get("error") == "captcha":
                        QApplication.processEvents()
                        reply = QMessageBox.question(self, "Google Captcha", 
                            f"Google требует пройти капчу для перевода. Открыть ссылку в браузере?\n\nПосле прохождения капчи попробуйте снова.",
                            QMessageBox.Yes | QMessageBox.No)
                        if reply == QMessageBox.Yes:
                            QDesktopServices.openUrl(result["url"])
                        progress.cancel()
                        return
                    else:
                        QMessageBox.warning(self, "Translation Error", 
                            f"Ошибка перевода: {result.get('message', 'Unknown error')}")
                        self.table.setItem(i, self.table.columnCount() - 1, QTableWidgetItem(""))
                else:
                    self.table.setItem(i, self.table.columnCount() - 1, QTableWidgetItem(show_po_text(result)))
                progress.setValue(i + 1)
                QApplication.processEvents()
        progress.close()

    def add_key(self):
        msgid_dlg = MultilineInputDialog("New key", "msgid:")
        if msgid_dlg.exec() != QDialog.Accepted:
            return
        msgid = msgid_dlg.get_text().strip()
        
        if not msgid:
            QMessageBox.warning(self, "Error", "msgid cannot be empty")
            return
            
        if self._check_msgid_exists(msgid):
            QMessageBox.warning(self, "Error", "This msgid already exists")
            return
            
        ru_dlg = MultilineInputDialog("Russian text", "Введите текст:")
        if ru_dlg.exec() != QDialog.Accepted:
            return
            
        asyncio.run(self._add_key_async(msgid, ru_dlg.get_text(), ru_dlg.translate_others))

    async def _add_key_async(self, msgid, ru_text, translate_others=False, source_lang=BASE_LANG):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(msgid))
        self._original_msgids[row] = msgid
        ru_text = save_po_text(ru_text)
        self.table.setItem(row, 1, QTableWidgetItem(show_po_text(ru_text)))
        langs = self.manager.locales[1:]
        if translate_others:
            source_index = self.manager.locales.index(source_lang)
            source_text = save_po_text(self.table.item(row, source_index + 1).text())
        else:
            source_text = ru_text
        progress = QProgressDialog("Translating key...", "Cancel", 0, len(langs), self)
        progress.setMinimumDuration(0)
        progress.show()
        QApplication.processEvents()
        async with aiohttp.ClientSession() as session:
            for i, lang in enumerate(langs):
                if progress.wasCanceled():
                    break
                if lang == source_lang:
                    text = source_text
                else:
                    result = await translate_text(session, source_text, source_lang, lang)
                    if isinstance(result, dict):
                        if result.get("error") == "captcha":
                            QApplication.processEvents()
                            reply = QMessageBox.question(self, "Google Captcha", 
                                f"Google требует пройти капчу для перевода. Открыть ссылку в браузере?\n\nПосле прохождения капчи попробуйте снова.",
                                QMessageBox.Yes | QMessageBox.No)
                            if reply == QMessageBox.Yes:
                                QDesktopServices.openUrl(result["url"])
                            progress.cancel()
                            return
                        else:
                            QMessageBox.warning(self, "Translation Error", 
                                f"Ошибка перевода: {result.get('message', 'Unknown error')}")
                            text = ""
                    else:
                        text = result
                self.table.setItem(row, i + 2, QTableWidgetItem(show_po_text(text)))
                QApplication.processEvents()
                progress.setValue(i + 1)
        progress.close()
        self.table.resizeColumnToContents(0)
        
        self._scroll_to_row(row)

    def _scroll_to_row(self, row):
        self.table.scrollToItem(self.table.item(row, 0))
        self.table.selectRow(row)
        self.table.setFocus()

    def show_cell_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item:
            return
        row = item.row()
        col = item.column()
        msgid = self.table.item(row, 0).text()
        menu = QMenu(self)
        edit_action = None
        if col != 0:
            edit_action = menu.addAction("✏ Edit text")
        delete_action = menu.addAction("🗑 Delete row")
        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action == delete_action:
            self.manager.delete_msgid(msgid)
            self.table.removeRow(row)
            self._reindex()
        elif action == edit_action:
            current = save_po_text(item.text())
            dlg = MultilineInputDialog("Edit translation", "Edit text:", current, with_translate=True)
            if dlg.exec() == QDialog.Accepted:
                source_lang = self.manager.locales[col - 1]
                asyncio.run(self._edit_and_translate(row, col, dlg.get_text(), dlg.translate_others, source_lang))

    async def _edit_and_translate(self, row, col, text, translate_others, source_lang):
        text = save_po_text(text)
        self.table.setItem(row, col, QTableWidgetItem(show_po_text(text)))
        if translate_others:
            langs = self.manager.locales
            progress = QProgressDialog("Translating...", "Cancel", 0, len(langs), self)
            progress.setMinimumDuration(0)
            progress.show()
            QApplication.processEvents()
            async with aiohttp.ClientSession() as session:
                for i, lang in enumerate(langs):
                    if progress.wasCanceled():
                        break
                    if lang == source_lang:
                        continue
                    result = await translate_text(session, text, source_lang, lang)
                    if isinstance(result, dict):
                        if result.get("error") == "captcha":
                            QApplication.processEvents()
                            reply = QMessageBox.question(self, "Google Captcha", 
                                f"Google требует пройти капчу для перевода. Открыть ссылку в браузере?\n\nПосле прохождения капчи попробуйте снова.",
                                QMessageBox.Yes | QMessageBox.No)
                            if reply == QMessageBox.Yes:
                                QDesktopServices.openUrl(result["url"])
                            progress.cancel()
                            return
                        else:
                            QMessageBox.warning(self, "Translation Error", 
                                f"Ошибка перевода: {result.get('message', 'Unknown error')}")
                            translated = ""
                    else:
                        translated = result
                    self.table.setItem(row, i + 1, QTableWidgetItem(show_po_text(translated)))
                    progress.setValue(i + 1)
                    QApplication.processEvents()
            progress.close()

    def show_header_context_menu(self, pos):
        col = self.table.horizontalHeader().logicalIndexAt(pos)
        if col <= 0:
            return
        lang = self.table.horizontalHeaderItem(col).text()
        if lang == BASE_LANG:
            return
        menu = QMenu(self)
        delete_action = menu.addAction("🗑 Delete language")
        action = menu.exec(self.table.horizontalHeader().mapToGlobal(pos))
        if action == delete_action:
            if QMessageBox.question(self, "Delete language",
                f"Delete language '{lang}' completely?",
                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                self.manager.delete_language(lang)
                self.table.removeColumn(col)
                self._adjust_lang_columns_width()

    def _reindex(self):
        self._original_msgids = {row: self.table.item(row, 0).text() for row in range(self.table.rowCount())}

    def on_item_changed(self, item):
        if item.column() != 0:
            return
        row = item.row()
        new = item.text().strip()
        old = self._original_msgids.get(row)
        
        if not new:
            item.setText(old)
            return
            
        if new == old:
            return
            
        if self._check_msgid_exists(new, exclude_row=row):
            QMessageBox.warning(self, "Error", "This msgid already exists")
            item.setText(old)
            return
            
        self.manager.rename_msgid(old, new)
        self._original_msgids[row] = new
        self.table.resizeColumnToContents(0)

    def save(self):
        for row in range(self.table.rowCount()):
            msgid = self.table.item(row, 0).text()
            for col, lang in enumerate(self.manager.locales, start=1):
                self.manager.update(msgid, lang, save_po_text(self.table.item(row, col).text()))
        self.manager.save_all()
        QMessageBox.information(self, "Saved", "Translations saved")

    def compile(self):
        self.manager.compile()
        QMessageBox.information(self, "Compiled", ".mo files compiled")

    def _adjust_lang_columns_width(self):
        if self.table.columnCount() <= 1:
            return
            
        first_col_width = self.table.columnWidth(0)
        total_width = self.table.viewport().width()
        
        if total_width <= 0:
            return
            
        available_width = total_width - first_col_width
        
        lang_cols = self.table.columnCount() - 1
        
        if lang_cols > 0:
            lang_col_width = max(150, available_width // lang_cols)
            for col in range(1, self.table.columnCount()):
                self.table.setColumnWidth(col, lang_col_width)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adjust_lang_columns_width()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = POEditor()
    window.show()
    sys.exit(app.exec())