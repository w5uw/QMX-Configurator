#!/usr/bin/env python3
"""
QMX+ Configurator - version 0.2.7 (staged read/write editing)

Browse every QMX/QMX+ configuration setting without PuTTY.
* Connect to the radio's USB COM port and read the full menu (CAT Menu Manager).
* Or open a saved snapshot (.json) with no radio connected.
* Search all settings, view band/schedule tables as grids, save snapshots.

Edits are staged and only written after Review / Apply; no transmit commands are sent.

Run on Windows 10:
    py -m pip install -r requirements.txt
    py qmx_configurator.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QThread, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDockWidget, QFileDialog,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

import qmx_protocol as qp

APP_NAME = "QMX+ Configurator"
APP_VERSION = "0.2.7"
TESTED_FIRMWARE = "1_04_010"
NODE_ROLE = Qt.UserRole + 1
# v0.2.7: folder the program files are in. File dialogs start here (or in the
# last folder used) instead of the Windows working folder, which is often
# C:\Windows\System32 when started from a shortcut.
APP_DIR = Path(__file__).resolve().parent

DANGER_FG = QColor("#b3261e")
MUTED_FG = QColor("#7a7a7a")
SUBMENU_FG = QColor("#1f5fa8")
PENDING_FG = QColor("#b35c00")


# --------------------------------------------------------------------------- worker
class ReadWorker(QThread):
    progress = Signal(str)
    log = Signal(str)
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, radio: qp.Radio):
        super().__init__()
        self.radio = radio
        self.disc = None

    def run(self):
        old_log = self.radio.log
        self.radio.log = self.log.emit
        try:
            self.disc = qp.Discoverer(self.radio, self.progress.emit)
            self.done.emit(self.disc.run())
        except Exception as e:                      # noqa: BLE001
            self.failed.emit(f"{type(e).__name__}: {e}")
        finally:
            self.radio.log = old_log

    def cancel(self):
        if self.disc:
            self.disc.cancel()


# --------------------------------------------------------------------------- helpers
def leaf_details(node: dict, lists: dict, inferred: dict | None = None) -> str:
    inferred = inferred or {}
    t = node.get("type")
    p = node.get("param", 0)
    if t in (5, 7):
        ch = lists.get(str(node.get("list_type")))
        if not ch:
            return f"List type {node.get('list_type')}"
        inf = inferred.get(str(node.get("list_type")))
        txt = " / ".join((f"{c} (filled in)" if inf is not None and c == inf else c) if c
                         else "(blank)" for c in ch)
        return txt if len(txt) <= 70 else txt[:67] + "..."
    if t == 2:
        return f"Text, up to {p} characters"
    if t in (3, 4):
        rng = qp.value_range(node)
        if rng is None:
            return "Number (digit limit not reported)"
        return f"Number {rng[0]} to {rng[1]} ({p} digit{'s' if p != 1 else ''})"
    if t == 6:
        return "Information only"
    if t == 8:
        return f"Decimal number, up to {p} characters (type 8, not in QRP Labs manual)"
    if t == 1:
        return "Action; run from the radio menu only"
    return ""


def fmt_value(node: dict, v):
    if v is None:
        return "(not readable)"
    if v == "":
        return "(empty)"
    return v


def band_label(v: str | None, col: int) -> str:
    if v and v.isdigit() and int(v) > 0:
        return f"{v}m"
    return f"Col {col + 1}"


# --------------------------------------------------------------------------- window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME}  {APP_VERSION}")
        self.resize(1200, 760)
        self.radio: qp.Radio | None = None
        self.worker: ReadWorker | None = None
        self.snapshot: dict | None = None
        self.lists: dict = {}
        self.inferred: dict = {}
        self._build_ui()
        self.refresh_ports()
        self._update_controls()

    # ---------------------------------------------------------------- layout
    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 4)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Port:"))
        self.port_box = QComboBox()
        self.port_box.setMinimumWidth(260)
        bar.addWidget(self.port_box)
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.refresh_ports)
        bar.addWidget(self.btn_refresh)
        self.btn_connect = QPushButton("Connect")
        self.btn_connect.clicked.connect(self.toggle_connect)
        bar.addWidget(self.btn_connect)
        self.lbl_radio = QLabel("Not connected")
        self.lbl_radio.setMinimumWidth(220)
        bar.addSpacing(12)
        bar.addWidget(self.lbl_radio)
        bar.addStretch(1)
        self.btn_read = QPushButton("Read all settings")
        self.btn_read.clicked.connect(self.read_all)
        bar.addWidget(self.btn_read)
        self.btn_open = QPushButton("Open snapshot...")
        self.btn_open.clicked.connect(self.open_snapshot)
        bar.addWidget(self.btn_open)
        self.btn_save = QPushButton("Save snapshot...")
        self.btn_save.clicked.connect(self.save_snapshot)
        bar.addWidget(self.btn_save)
        root.addLayout(bar)

        self.banner = QLabel("Read-only mode: this version never changes radio settings "
                             "and never transmits.")
        self.banner.setStyleSheet("background:#eef3f8; color:#22384f; padding:5px 8px;"
                                  "border:1px solid #c9d6e3; border-radius:3px;")
        root.addWidget(self.banner)

        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search settings and values...")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.on_search)
        lv.addWidget(self.search)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.currentItemChanged.connect(self.on_tree_select)
        lv.addWidget(self.tree)
        split.addWidget(left)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        self.lbl_section = QLabel("Open a snapshot or connect and read settings.")
        f = self.lbl_section.font()
        f.setPointSize(f.pointSize() + 2)
        f.setBold(True)
        self.lbl_section.setFont(f)
        rv.addWidget(self.lbl_section)
        self.lbl_warn = QLabel("")
        self.lbl_warn.setWordWrap(True)
        self.lbl_warn.setStyleSheet("background:#fdecea; color:#8a1c14; padding:5px 8px;"
                                    "border:1px solid #f1b8b2; border-radius:3px;")
        self.lbl_warn.hide()
        rv.addWidget(self.lbl_warn)
        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.cellDoubleClicked.connect(self.on_table_double)
        rv.addWidget(self.table)
        split.addWidget(right)
        split.setSizes([300, 900])
        root.addWidget(split, 1)
        self.setCentralWidget(central)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)
        self.log_view.setFont(QFont("Consolas", 9))
        dock = QDockWidget("Communication log", self)
        dock.setWidget(self.log_view)
        dock.setObjectName("logdock")
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)
        dock.hide()
        self.log_dock = dock

        view = self.menuBar().addMenu("&View")
        act = dock.toggleViewAction()
        act.setText("Communication log")
        view.addAction(act)
        helpm = self.menuBar().addMenu("&Help")
        about = QAction("About", self)
        about.triggered.connect(self.about)
        helpm.addAction(about)

        self.progress = QProgressBar()
        self.progress.setMaximumWidth(220)
        self.progress.setRange(0, 0)
        self.progress.hide()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.cancel_read)
        self.btn_cancel.hide()
        self.statusBar().addPermanentWidget(self.progress)
        self.statusBar().addPermanentWidget(self.btn_cancel)
        self.statusBar().showMessage("Ready")

    def _update_controls(self):
        busy = self.worker is not None
        connected = self.radio is not None
        self.btn_connect.setText("Disconnect" if connected else "Connect")
        self.btn_connect.setEnabled(not busy and (connected or self.port_box.count() > 0))
        self.port_box.setEnabled(not connected and not busy)
        self.btn_refresh.setEnabled(not connected and not busy)
        self.btn_read.setEnabled(connected and not busy)
        self.btn_open.setEnabled(not busy)
        self.btn_save.setEnabled(self.snapshot is not None and not busy)

    def log(self, s: str):
        self.log_view.appendPlainText(s)

    # ---------------------------------------------------------------- connection
    def refresh_ports(self):
        self.port_box.clear()
        for dev, desc in qp.available_ports():
            self.port_box.addItem(f"{dev}  -  {desc}" if desc else dev, dev)
        if self.port_box.count() == 0:
            self.port_box.addItem("(no serial ports found)", None)
        self._update_controls()

    def toggle_connect(self):
        if self.radio:
            self.radio.close()
            self.radio = None
            self.lbl_radio.setText("Not connected")
            self.log("Disconnected.")
            self._update_controls()
            return
        port = self.port_box.currentData()
        if not port:
            return
        try:
            self.radio = qp.Radio(port, log=self.log)
        except Exception as e:                       # noqa: BLE001
            msg = str(e)
            hint = ("\n\nThe port may be in use. Close PuTTY or other radio software and try again."
                    if "denied" in msg.lower() or "busy" in msg.lower() else "")
            QMessageBox.warning(self, APP_NAME, f"Could not open {port}:\n{msg}{hint}")
            self.radio = None
            return
        fw = qp.body(self.radio.query("VN;"), "VN")
        if fw is None:
            self.radio.close()
            self.radio = None
            QMessageBox.warning(self, APP_NAME, f"{port} opened, but no radio answered.\n"
                                "Check that this is the QMX+ port and the radio is on.")
            return
        self.lbl_radio.setText(f"Connected on {port}  |  firmware {fw}")
        self.statusBar().showMessage(f"Connected to {port}")
        if TESTED_FIRMWARE not in fw:
            QMessageBox.information(self, APP_NAME,
                                    f"Firmware {fw} differs from the tested version "
                                    f"({TESTED_FIRMWARE}). Reading should still work, but "
                                    "check results carefully.")
        self._update_controls()

    # ---------------------------------------------------------------- read
    def read_all(self):
        if not self.radio:
            return
        self.worker = ReadWorker(self.radio)
        self.worker.progress.connect(lambda p: self.statusBar().showMessage(f"Reading: {p}"))
        self.worker.log.connect(self.log)
        self.worker.done.connect(self.on_read_done)
        self.worker.failed.connect(self.on_read_failed)
        self.worker.finished.connect(self.on_worker_finished)
        self.progress.show()
        self.btn_cancel.show()
        self._update_controls()
        self.worker.start()

    def cancel_read(self):
        if self.worker:
            self.worker.cancel()
            self.statusBar().showMessage("Cancelling...")

    def on_read_done(self, snap: dict):
        if snap.get("cancelled"):
            self.statusBar().showMessage("Read cancelled; partial results shown.")
        else:
            self.statusBar().showMessage(
                f"Read complete: {snap['commands_sent']} commands.", 8000)
        self.load_snapshot(snap)

    def on_read_failed(self, msg: str):
        QMessageBox.warning(self, APP_NAME, f"Reading failed:\n{msg}")
        self.statusBar().showMessage("Read failed")

    def on_worker_finished(self):
        self.worker = None
        self.progress.hide()
        self.btn_cancel.hide()
        self._update_controls()

    # ---------------------------------------------------------------- snapshots
    def file_dir(self) -> Path:
        """Folder for Open/Save dialogs: the last folder used, else the program folder."""
        last = QSettings().value("last_dir", "")
        if last and Path(last).is_dir():
            return Path(last)
        return APP_DIR

    def file_path(self, name: str) -> str:
        """Full default path for a save dialog, in file_dir()."""
        return str(self.file_dir() / name)

    def remember_dir(self, path: str):
        """Remember the folder of a file the user just opened or saved."""
        if path:
            QSettings().setValue("last_dir", str(Path(path).resolve().parent))

    def open_snapshot(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open snapshot", str(self.file_dir()),
                                              "QMX snapshot (*.json);;All files (*)")
        if not path:
            return
        self.remember_dir(path)
        try:
            snap = json.loads(Path(path).read_text(encoding="utf-8"))
            if "menu" not in snap:
                raise ValueError("file has no 'menu' section")
        except Exception as e:                       # noqa: BLE001
            QMessageBox.warning(self, APP_NAME, f"Could not open snapshot:\n{e}")
            return
        self.load_snapshot(snap)
        self.statusBar().showMessage(f"Opened {Path(path).name}", 8000)

    def save_snapshot(self):
        if not self.snapshot:
            return
        fw = (self.snapshot.get("firmware") or "unknown").replace("/", "_")
        stamp = (self.snapshot.get("generated") or "").replace(":", "").replace("-", "")
        default = f"qmx_snapshot_{fw}_{stamp}.json"
        path, _ = QFileDialog.getSaveFileName(self, "Save snapshot", self.file_path(default),
                                              "QMX snapshot (*.json)")
        if path:
            self.remember_dir(path)
            Path(path).write_text(json.dumps(self.snapshot, indent=2), encoding="utf-8")
            self.statusBar().showMessage(f"Saved {Path(path).name}", 8000)

    def load_snapshot(self, snap: dict):
        self.snapshot = snap
        self.lists = {k: qp.clean_list(v) for k, v in (snap.get("lists") or {}).items()}
        self.inferred = qp.repair_lists(self.lists, snap["menu"])
        self.tree.clear()
        self._add_tree(self.tree.invisibleRootItem(), snap["menu"], False)
        src = snap.get("port") or "file"
        self.setWindowTitle(f"{APP_NAME}  {APP_VERSION}  -  firmware "
                            f"{snap.get('firmware')}  ({src}, {snap.get('generated')})")
        self._update_controls()
        first = self.tree.topLevelItem(0)
        if first:
            self.tree.setCurrentItem(first)

    def _add_tree(self, parent, nodes, in_danger):
        for n in nodes:
            if n.get("type") != 0:
                continue
            danger = in_danger or qp.is_dangerous(n["name"])
            label = n["name"] + (f"  [{n['grid_columns']} columns]" if "grid_columns" in n else "")
            it = QTreeWidgetItem([("LOCKED  " if danger else "") + label])
            it.setData(0, NODE_ROLE, (n, danger))
            if danger:
                it.setForeground(0, QBrush(DANGER_FG))
            parent.addChild(it)
            self._add_tree(it, n.get("children", []), danger)

    # ---------------------------------------------------------------- views
    def on_tree_select(self, cur, _prev):
        if not cur or self.search.text():
            return
        node, danger = cur.data(0, NODE_ROLE)
        self.show_section(node, danger)

    def refresh_view(self):
        """Redraw the table that is currently shown (section or search results)."""
        if self.search.text().strip():
            self.on_search(self.search.text())
        else:
            cur = self.tree.currentItem()
            if cur:
                self.on_tree_select(cur, None)

    def show_section(self, node, danger):
        self.lbl_section.setText(node["path_names"].replace("|", "  >  "))
        if danger:
            self.lbl_warn.setText("Locked section. QRP Labs marks these settings as "
                                  "dangerous. They are shown for reference only and will "
                                  "stay locked when editing is added.")
            self.lbl_warn.show()
        else:
            self.lbl_warn.hide()
        children = node.get("children", [])
        if "grid_columns" in node:
            self.show_grid(node, children)
        else:
            self.show_list(children, danger, with_path=False)

    def _item(self, text, fg=None, bold=False, tip=None):
        it = QTableWidgetItem(text)
        if fg is not None:
            it.setForeground(QBrush(fg))
        if bold:
            f = it.font()
            f.setBold(True)
            it.setFont(f)
        if tip:
            it.setToolTip(tip)
        return it

    def show_list(self, rows, danger, with_path):
        headers = (["Location"] if with_path else []) + ["Setting", "Value", "Type", "Details"]
        self.table.clear()
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(rows))
        for r, entry in enumerate(rows):
            n, row_danger = entry if isinstance(entry, tuple) else (entry, danger)
            c = 0
            if with_path:
                loc = " > ".join(n["path_names"].split("|")[:-1])
                self.table.setItem(r, c, self._item(loc, MUTED_FG))
                c += 1
            t = n.get("type")
            name_fg = DANGER_FG if row_danger else None
            if t == 0:
                suffix = f"  [{n['grid_columns']} columns]" if "grid_columns" in n else ""
                self.table.setItem(r, c, self._item(n["name"] + suffix, SUBMENU_FG, True))
                self.table.setItem(r, c + 1, self._item("Open >", SUBMENU_FG))
                self.table.setItem(r, c + 2, self._item("Sub-menu", MUTED_FG))
                self.table.setItem(r, c + 3, self._item("Double-click to open", MUTED_FG))
            else:
                self.table.setItem(r, c, self._item(n.get("name", n.get("raw", "?")), name_fg))
                if "values" in n:
                    v = ", ".join(x or "-" for x in n["values"])
                    val_item = self._item(v[:60] + ("..." if len(v) > 60 else ""), tip=v)
                elif t == 1:
                    val_item = self._item("-", MUTED_FG)
                else:
                    raw = n.get("value")
                    pend = self.pending_value(n.get("path_index"))
                    if pend is not None:
                        val_item = self._item(fmt_value(n, pend) + "   (pending)", PENDING_FG,
                                              bold=True,
                                              tip=f"Staged, not yet written: {pend!r}\n"
                                                  f"Last read from radio: {raw!r}")
                    else:
                        shown = fmt_value(n, raw)
                        val_item = self._item(shown,
                                              MUTED_FG if raw in (None, "") else None,
                                              bold=raw not in (None, ""), tip=shown)
                self.table.setItem(r, c + 1, val_item)
                self.table.setItem(r, c + 2, self._item(qp.TYPE_NAMES.get(t, str(t)), MUTED_FG))
                det = leaf_details(n, self.lists, self.inferred)
                full = None
                if t in (5, 7):
                    ch = self.lists.get(str(n.get("list_type"))) or []
                    full = "\n".join(c2 if c2 else "(blank)" for c2 in ch)
                    lt = str(n.get("list_type"))
                    if lt in self.inferred:
                        full += (f"\n\nThe radio's list reply was missing a choice; "
                                 f"'{self.inferred[lt]}' was filled in from the current value.")
                self.table.setItem(r, c + 3, self._item(det, MUTED_FG, tip=full or det))
            self.table.item(r, c).setData(NODE_ROLE, (n, row_danger))
        self._size_columns(len(headers))

    def _size_columns(self, count):
        """Fit columns to their contents once, then let the user drag them wider or narrower."""
        hh = self.table.horizontalHeader()
        hh.setStretchLastSection(True)
        for i in range(count):
            hh.setSectionResizeMode(i, QHeaderView.Interactive)
        self.table.resizeColumnsToContents()
        for i in range(count - 1):
            w = self.table.columnWidth(i)
            self.table.setColumnWidth(i, max(60, min(w + 12, 520)))

    def pending_value(self, path):
        """Value staged for path but not yet written (editing window overrides this)."""
        return None

    def show_grid(self, node, rows):
        cols = node["grid_columns"]
        name_row = next((r for r in rows if r.get("name", "").lower().startswith("band name")), None)
        if name_row and "values" in name_row:
            labels = [band_label(name_row["values"][i], i) for i in range(cols)]
            used = [lbl.endswith("m") for lbl in labels]
        else:
            labels = [str(i + 1) for i in range(cols)]
            used = [True] * cols
        self.table.clear()
        self.table.setColumnCount(cols + 1)
        self.table.setHorizontalHeaderLabels(["Setting"] + labels)
        self.table.setRowCount(len(rows))
        for r, n in enumerate(rows):
            self.table.setItem(r, 0, self._item(n.get("name", "?"), bold=True,
                                                tip=leaf_details(n, self.lists, self.inferred)))
            vals = n.get("values") or [n.get("value")] * cols
            for c in range(cols):
                v = vals[c] if c < len(vals) else None
                pend = self.pending_value(f"{n.get('path_index')}[{c}]")
                if pend is not None:
                    cell = self._item(fmt_value(n, pend) + " *", PENDING_FG, bold=True,
                                      tip=f"Staged, not yet written: {pend!r}\nLast read from radio: {v!r}")
                else:
                    cell = self._item(fmt_value(n, v), None if used[c] else MUTED_FG)
                self.table.setItem(r, c + 1, cell)
            self.table.item(r, 0).setData(NODE_ROLE, (n, False))
        self._size_columns(cols + 1)

    def on_table_double(self, row, _col):
        it = self.table.item(row, 0)
        data = it.data(NODE_ROLE) if it else None
        if data is None:
            it = self.table.item(row, 1)
            data = it.data(NODE_ROLE) if it else None
        if not data or data[0].get("type") != 0:
            return
        target = data[0]["path_index"]
        it = self._find_tree(self.tree.invisibleRootItem(), target)
        if it:
            self.search.clear()
            self.tree.setCurrentItem(it)
            it.setExpanded(True)

    def _find_tree(self, parent, path_index):
        for i in range(parent.childCount()):
            ch = parent.child(i)
            n, _ = ch.data(0, NODE_ROLE)
            if n["path_index"] == path_index:
                return ch
            found = self._find_tree(ch, path_index)
            if found:
                return found
        return None

    def on_search(self, text):
        if not self.snapshot:
            return
        text = text.strip().lower()
        if not text:
            cur = self.tree.currentItem()
            if cur:
                self.on_tree_select(cur, None)
            return
        hits = []

        def walk(nodes, danger):
            for n in nodes:
                if "name" not in n:
                    continue
                d = danger or qp.is_dangerous(n["name"])
                if n.get("type") != 0:
                    hay = n["path_names"].lower() + " " + str(n.get("value") or "").lower()
                    if text in hay:
                        hits.append((n, d))
                walk(n.get("children", []), d)

        walk(self.snapshot["menu"], False)
        self.lbl_section.setText(f"Search results for \u201c{text}\u201d: {len(hits)}")
        self.lbl_warn.hide()
        self.show_list(hits, False, with_path=True)

    def about(self):
        QMessageBox.about(self, APP_NAME,
                          f"<b>{APP_NAME}</b> {APP_VERSION}<br><br>"
                          "Browse QRP Labs QMX/QMX+ configuration settings over the USB "
                          "serial port using CAT Menu Manager commands (MM, ML).<br><br>"
                          f"Tested with firmware {TESTED_FIRMWARE}. Conservative staged editing; some setting types remain locked.")

    def closeEvent(self, e):
        if self.worker:
            self.worker.cancel()
            self.worker.wait(3000)
        if self.radio:
            self.radio.close()
        super().closeEvent(e)


from qmx_editing import make_window
MainWindow = make_window(MainWindow)

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setOrganizationName("W5UW")          # QSettings location (remembers the last folder)
    app.setApplicationName(APP_NAME)
    w = MainWindow()
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".json"):
        try:
            w.load_snapshot(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
        except Exception as e:                       # noqa: BLE001
            QMessageBox.warning(w, APP_NAME, f"Could not open {sys.argv[1]}:\n{e}")
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
