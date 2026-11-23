"""Conservative staged editing extension for QMX+ Configurator."""
import json
import re
from datetime import datetime
from pathlib import Path
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QInputDialog,
                               QLabel, QLineEdit, QMessageBox, QVBoxLayout)

import qmx_protocol as qp

APP_VERSION = "0.2.4"

# v0.2.1: settings inside System config -> CAT config that may be edited.
# Names are compared after lower-casing and removing everything except a-z/0-9,
# so "Timeout (s)" -> "timeouts", "KY TS480" -> "kyts480".
# Any other (e.g. future) CAT config item stays locked.
CAT_CONFIG_EDITABLE = {"kyts480", "ruandrd", "mmeffect", "timeout", "timeouts"}
CAT_TIMEOUT_SECONDS = (10, 600)   # accepted range for CAT config -> Timeout (s)
OFF_WORDS = {"disabled", "off", "no"}


def _norm(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def cat_config_item(node):
    """Return the normalised item name if node is directly inside CAT config, else None."""
    parts = node.get("path_names", "").split("|")
    if len(parts) >= 2 and _norm(parts[-2]) == "catconfig":
        return _norm(parts[-1])
    return None

PROTECTION_EDITABLE = {
    "swrprotection", "swrthreshold", "protectionreset", "swrtimeout",
    "swrwarnstyle", "tune", "gpsprotection", "supplyvoltage",
    "minvoltage", "maxvoltage",
}

def in_virtual_u3s(node):
    return any(_norm(part) == "virtualu3s"
               for part in node.get("path_names", "").split("|"))

def protection_item(node):
    parts = node.get("path_names", "").split("|")
    if len(parts) == 2 and _norm(parts[0]) == "protection":
        return _norm(parts[1])
    return None

def make_window(Base):
    class EditingWindow(Base):
        def __init__(self):
            self.pending = {}
            self.live_snapshot = False
            super().__init__()
            self.banner.setText("Read/write version: read the connected radio first; double-click a value to stage an edit. Apply requires confirmation. No transmit commands are sent.")
            toolbar = self.addToolBar("Configuration editing")
            toolbar.addAction("Review / Apply changes", self.apply_changes)
            toolbar.addAction("Discard pending changes", self.discard_changes)
            self.setWindowTitle(f"QMX+ Configurator {APP_VERSION} — staged editing")

        def pending_value(self, path):
            p = self.pending.get(path) if path else None
            return p["new"] if p else None

        def edit_text(self, node, current):
            """Wide single-line editor for Text settings (e.g. 50-character messages)."""
            limit = node.get("param", 0)
            dlg = QDialog(self)
            dlg.setWindowTitle("Stage edit")
            lay = QVBoxLayout(dlg)
            lay.addWidget(QLabel(node["path_names"].replace("|", "  >  ")))
            edit = QLineEdit(current)
            edit.setMaxLength(limit)
            edit.setMinimumWidth(max(420, edit.fontMetrics().horizontalAdvance("W") * min(limit, 60)))
            lay.addWidget(edit)
            count = QLabel()
            note = QLabel("The radio may store letters in upper case; read-back ignores "
                          "upper/lower case for text settings.")
            note.setWordWrap(True)
            note.setStyleSheet("color:#7a7a7a")
            def upd():
                count.setText(f"{len(edit.text())} of {limit} characters")
            edit.textChanged.connect(upd)
            upd()
            lay.addWidget(count)
            lay.addWidget(note)
            bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            bb.accepted.connect(dlg.accept)
            bb.rejected.connect(dlg.reject)
            lay.addWidget(bb)
            ok = dlg.exec() == QDialog.Accepted
            return edit.text(), ok

        @staticmethod
        def values_match(node, actual, expected):
            """Read-back check. Text is compared ignoring case because the radio may
            convert letters (a typed 'cq' reads back as 'CQ'); all else must be exact."""
            if actual == expected:
                return True
            if node.get("type") == 2 and actual is not None:
                return actual.casefold() == expected.casefold()
            return False

        def store_read_back(self, node, sub, actual):
            """Put a verified read-back value into the in-memory snapshot so the table shows it."""
            if sub is None:
                node["value"] = actual
            else:
                node["values"][sub] = actual

        def load_snapshot(self, snap):
            self.pending.clear()
            self.live_snapshot = False
            super().load_snapshot(snap)

        def on_read_done(self, snap):
            super().on_read_done(snap)
            self.live_snapshot = not snap.get("cancelled", False)

        def toggle_connect(self):
            self.live_snapshot = False
            self.pending.clear()
            super().toggle_connect()

        def discard_changes(self):
            self.pending.clear()
            self.refresh_view()
            self.statusBar().showMessage("Pending edits discarded; nothing written.")

        def confirm_discard(self):
            return not self.pending or QMessageBox.question(self, "Discard pending edits?", "This will discard all staged edits. Continue?") == QMessageBox.Yes

        def read_all(self):
            if self.confirm_discard():
                self.pending.clear()
                self.live_snapshot = False
                super().read_all()

        def open_snapshot(self):
            if self.confirm_discard():
                super().open_snapshot()

        def locked(self, node):
            parts = node.get("path_names", "").split("|")
            if any(qp.is_dangerous(x) for x in parts):
                return True
            # Explicit dangerous paths above remain locked.
            item = protection_item(node)
            if item is not None:
                return item not in PROTECTION_EDITABLE
            if in_virtual_u3s(node):
                return False
            # v0.2.1: CAT config is no longer locked as a whole; only the
            # reviewed items in CAT_CONFIG_EDITABLE may be edited.
            item = cat_config_item(node)
            if item is not None:
                return item not in CAT_CONFIG_EDITABLE
            # Keep calibration, protection, automatic transmit and connectivity settings locked.
            extra = ("calibr", "tcxo", "protection", "pa voltage", "virtual u3s", "beacon", "wspr", "schedule", "gps", "ptt", "vox", "transmit", "tx ", "tune", "firmware")
            text = " ".join(parts).lower()
            return any(x in text for x in extra)

        def validate(self, node, value):
            t, limit = node.get("type"), node.get("param", 0)
            if self.locked(node) or t not in (2, 3, 4, 5):
                raise ValueError("This setting is locked or its field type is not supported for editing.")
            if any(ord(c) < 32 or ord(c) > 126 or c in ";=|?[]" for c in value):
                raise ValueError("Only printable ASCII without CAT delimiters is supported.")
            if t == 2 and (not isinstance(limit, int) or limit < 1 or len(value) > limit):
                raise ValueError("Text exceeds the discovered field length.")
            if t in (3, 4):
                if not re.fullmatch(r"[0-9]+", value):
                    raise ValueError("Enter an unsigned whole number.")
                rng = qp.value_range(node)
                if rng is None:
                    raise ValueError("The radio did not report a digit limit for this number.")
                lo, hi = rng
                if not lo <= int(value) <= hi or len(value) > limit:
                    raise ValueError(f"Enter a whole number from {lo} to {hi} "
                                     f"(this field holds {limit} digit{'s' if limit != 1 else ''}).")
                if cat_config_item(node) == "timeouts":
                    lo, hi = CAT_TIMEOUT_SECONDS
                    if not lo <= int(value) <= hi:
                        raise ValueError(f"CAT timeout must be {lo} to {hi} seconds.")
            if t == 5:
                lt = str(node.get("list_type"))
                choices = self.lists.get(lt) or []
                if lt in self.inferred or lt in ("8", "34") or lt in self.snapshot.get("damaged_lists", []) or not choices or "" in choices or len(set(choices)) != len(choices):
                    raise ValueError("This option list is incomplete or ambiguous and remains locked.")
                if value not in choices:
                    raise ValueError("Choose a discovered list value.")

        def on_table_double(self, row, col):
            data = None
            for c in (0, 1):
                item = self.table.item(row, c)
                if item and item.data(257) is not None:
                    data = item.data(257)
                    break
            if not data:
                return
            node, danger = data
            if node.get("type") == 0:
                return super().on_table_double(row, col)
            if self.worker or not self.radio or not self.live_snapshot:
                QMessageBox.information(self, "Read first", "Connect and complete Read all settings before editing.")
                return
            sub = None
            if "values" in node:
                if self.search.text() or col < 1:
                    QMessageBox.information(self, "Grid edit", "Open the grid section and double-click the individual value cell.")
                    return
                sub = col - 1
                if sub >= len(node["values"]):
                    return
                old = node["values"][sub]
            else:
                old = node.get("value")
            if danger or old is None:
                QMessageBox.warning(self, "Locked", "This setting is locked or has no readable current value.")
                return
            path = node["path_index"] + (f"[{sub}]" if sub is not None else "")
            current = self.pending.get(path, {}).get("new", old)
            try:
                self.validate(node, current)
            except ValueError as exc:
                QMessageBox.information(self, "Locked", str(exc))
                return
            if node["type"] == 5:
                choices = self.lists[str(node["list_type"]) ]
                value, ok = QInputDialog.getItem(self, "Stage edit", node["path_names"], choices, choices.index(current), False)
            elif node["type"] == 2:
                value, ok = self.edit_text(node, current)
            else:
                rng = qp.value_range(node)
                label = node["path_names"].replace("|", "  >  ")
                if rng:
                    label += f"\n\nAllowed: {rng[0]} to {rng[1]}"
                value, ok = QInputDialog.getText(self, "Stage edit", label, text=current)
                value = value.strip()
            if not ok:
                return
            try:
                self.validate(node, value)
            except ValueError as exc:
                QMessageBox.warning(self, "Invalid value", str(exc))
                return
            if value != old and not self.confirm_special(node, value):
                return
            if value == old:
                self.pending.pop(path, None)
            else:
                self.pending[path] = dict(node=node, sub=sub, old=old, new=value)
            self.refresh_view()
            self.statusBar().showMessage(f"{len(self.pending)} pending change(s), shown in orange. Radio unchanged until Apply.")

        def confirm_special(self, node, value):
            """Extra explanation/confirmation for CAT config items. Returns True to stage."""
            if protection_item(node) is not None:
                return QMessageBox.warning(
                    self, "Stage Protection setting?",
                    "Protection settings control safeguards for the radio. "
                    "Disabling protection or changing thresholds can reduce those "
                    "safeguards and may expose the radio to damage.\n\n"
                    f"Setting: {node['path_names']}\nNew value: {value}\n\n"
                    "Numeric validation checks the CAT field format, not whether "
                    "the value is electrically safe for your hardware. Changes "
                    "may take effect immediately when applied.\n\n"
                    "Stage this change?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No) == QMessageBox.Yes
            if in_virtual_u3s(node):
                return QMessageBox.warning(
                    self, "Stage Virtual U3S setting?",
                    "Virtual U3S settings can control automatic beacon or scheduled "
                    "transmissions. Applying an enable, mode, frequency, power or "
                    "schedule change may affect transmission immediately or when "
                    "the radio activates the saved settings.\n\n"
                    "This editor does not execute menu actions or send a separate "
                    "transmit command, but configuration changes are not a guarantee "
                    "that the radio will remain in receive.\n\n"
                    "Confirm the radio is prepared for the resulting operation. "
                    "Stage this change?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No) == QMessageBox.Yes
            item = cat_config_item(node)
            if item == "timeout" and _norm(value) in OFF_WORDS:
                return QMessageBox.warning(
                    self, "Disable CAT timeout?",
                    "The CAT timeout is a safety feature: if a program puts the radio into "
                    "transmit and then stops sending commands, the radio returns to receive "
                    "when the timeout expires.\n\nWith it disabled, a crashed or disconnected "
                    "program could leave the radio transmitting. QRP Labs advises disabling it "
                    "only when using VOX.\n\nStage this change anyway?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes
            if item == "mmeffect":
                QMessageBox.information(
                    self, "MM Effect",
                    "MM Effect controls when settings written by this app take effect:\n\n"
                    "On demand: after you enter and exit the radio's menu.\n"
                    "Immediate: as soon as each setting is written.\n\n"
                    "The new MM Effect value itself may only become active after the next "
                    "menu enter/exit on the radio.")
            return True

        def get_value(self, path):
            reply = self.radio.query("MM" + path + ";")
            if not reply or not reply.startswith("MM") or not reply.endswith(";"):
                raise RuntimeError("Invalid or missing read-back for " + path)
            return reply[2:-1]

        def apply_changes(self):
            if self.worker or not self.radio or not self.live_snapshot or not self.pending:
                QMessageBox.information(self, "Apply", "Read the connected radio and stage at least one edit first.")
                return
            lines = [f"{v['node']['path_names']} ({k}): {v['old']!r} → {v['new']!r}" for k, v in self.pending.items()]
            box = QMessageBox(self)
            box.setWindowTitle("Confirm configuration writes")
            box.setText(f"Write {len(lines)} change(s) to radio configuration memory?\n\nThe main table still shows the last read values. No automatic rollback is attempted. A failure can leave a partially changed configuration.\n\nChanges may take effect immediately, depending on MM Effect.")
            box.setDetailedText("\n".join(lines))
            box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            box.setDefaultButton(QMessageBox.No)
            if box.exec() != QMessageBox.Yes:
                return
            filename, _ = QFileDialog.getSaveFileName(self, "Save pre-write backup (required)", "qmx_before_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json", "JSON (*.json)")
            if not filename:
                return
            verified = []
            ok_all = False
            try:
                # Re-read all affected values before the first write, catching external changes.
                for path, v in self.pending.items():
                    self.validate(v["node"], v["new"])
                    if self.get_value(path) != v["old"]:
                        raise RuntimeError("Radio value changed since discovery: " + path + ". Read all settings again.")
                Path(filename).write_text(json.dumps(self.snapshot, indent=2), encoding="utf-8")
                for path, v in self.pending.items():
                    reply = self.radio.write_setting(path, v["new"])
                    if reply and reply.startswith("?"):
                        raise RuntimeError("Radio rejected write: " + path)
                    actual = self.get_value(path)
                    if not self.values_match(v["node"], actual, v["new"]):
                        self.store_read_back(v["node"], v["sub"], actual)
                        hint = (" The radio may have limited the number to its own range."
                                if v["node"].get("type") in (3, 4) else "")
                        raise RuntimeError(f"Write unverified at {v['node']['path_names']} ({path}): "
                                           f"read back {actual!r}, expected {v['new']!r}.{hint} No further writes sent.")
                    if actual != v["new"]:
                        self.log(f"NOTE {path}: radio stored {actual!r} for {v['new']!r} (case differs only); accepted.")
                    self.store_read_back(v["node"], v["sub"], actual)
                    verified.append(path)
                ok_all = True
                QMessageBox.information(self, "Writes verified", f"{len(verified)} setting(s) read back correctly. The table now shows the values read back from the radio.\n\nNo MU reload command was sent. If MM Effect is On demand, enter and exit the radio menu to activate the saved configuration.")
            except Exception as exc:
                self.log("APPLY STOPPED: " + str(exc))
                QMessageBox.warning(self, "Apply stopped", f"{exc}\n\n{len(verified)} preceding write(s) verified. The failed setting may already have changed. No automatic rollback. Read all settings before further edits.")
            finally:
                self.pending.clear()
                # Every written value was read back, so the snapshot still matches the
                # radio after a fully verified Apply; after a failure, require a re-read.
                self.live_snapshot = ok_all
                self.refresh_view()
                self.statusBar().showMessage(
                    f"Apply finished: {len(verified)} write(s) verified." if ok_all else
                    f"Apply stopped after {len(verified)} verified write(s). Read all settings before further edits.")

        def closeEvent(self, event):
            if self.worker:
                QMessageBox.information(self, "Read in progress", "Cancel the read and wait for it to finish before closing.")
                event.ignore()
                return
            if not self.confirm_discard():
                event.ignore()
                return
            super().closeEvent(event)

    return EditingWindow