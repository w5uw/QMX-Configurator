QMX+ This is a Windows GUI program developed by me Laurance Brungardt W5UW
that allows you to view and edit all the menu settings you would normally
have to access through PUTTY - Make a folder called QMX_Configurator copy
the files from the repository to that folder and then create a desktop ICON
pointing to the QMX_configurator.py file and that's it baby!
Enjoy

## Release notes

### v0.2.8 (2026-11-24)

Tested on a QMX+ with firmware 1_04_010, together with the v0.2.7 fixes.

Decimal editing for the two PA voltage settings.

- Protection > Max. PA voltage and Virtual U3S > PA Voltage can now be edited.
  Enter volts from 1.00 to 12.0, for example 6.00 or 11.5. Below 10 V the radio
  holds two decimal places, 10 V and above one; anything else is refused.
- The app checks the range itself because the radio stores whatever it is sent
  over CAT (a typed "120" would be 120 V).
- Each change asks for confirmation, with a warning above the 11.5 V factory
  default, above 9 V for 9 V-built radios, and when the U3S PA Voltage is
  higher than Max. PA voltage.
- Read-back compares the voltage by value, so 6.0 and 6.00 match.
- If the radio returns a voltage without a decimal point (Display/controls >
  Thousands delimiter set to "." on some firmware), editing is locked with an
  explanation, because the real value can't be known.
- Other decimal settings (for example TCXO Cal Error) stay read-only.

### v0.2.7 (2026-11-24)

Bug fixes reported by Stan KC7XE. Tested on a QMX+ with firmware 1_04_010.

- Open and Save dialogs (snapshot and the pre-write backup) now start in the
  QMX_Configurator program folder instead of C:\Windows\System32, and after
  that in the last folder you used. The folder is remembered between runs.
- Messages and other text settings can be cleared. The radio refuses an empty
  value, so deleting all the text now writes a single space, and read-back
  accepts a blank or a space. Previously Apply stopped with "Radio rejected
  write: 5|6".
- When the radio refuses a write, the message now names the setting and the
  value sent, not just its menu number (5|6 means menu 5, item 6).

### v0.2.6 (2026-11-23)

Release covering v0.2.4 to v0.2.6. Tested on a QMX+ with firmware 1_04_010.

Highlights:

- Number and Byte settings use the real range the radio reports (for example
  USB Audio Gain and Monitor 0 to 99) instead of always 0 to 255.
- The Messages table is readable: resizable columns, pending edits shown in
  orange, and values refreshed from the radio after Apply.
- Read-back no longer stops a batch over letter case ("cq" stored as "CQ") or
  leading zeros.
- Set time is handled as the radio's running clock, entered as HHMM.
- A stopped Apply no longer forces a full Read all settings before editing again.

Upgrading: copy the new .py files over your QMX_Configurator folder (keep a
backup of the old folder). Your saved snapshots still open. Requirements are
unchanged (see requirements.txt).

Still read-only (as of v0.2.6; see v0.2.8 for PA voltages): PA Voltage and
Max. PA voltage (decimal format not yet supported), calibration, mask fields, actions, and the Delimiter and GPS NMEA
lists. Number limits come from each field's digit count, not from what is
electrically safe for your hardware.

### Detailed changes

#### v0.2.6

- Set time (Virtual U3S and System config) is treated as the radio's running
  clock: entered as HHMM (0000-2359), not blocked by the "changed since read"
  check, and read-back allows the clock to tick by one minute.
- If an Apply stops, the staged settings are re-read from the radio and the
  table refreshed, so editing can continue without a full Read all settings.
- The "changed since read" message now names the setting and both values.

#### v0.2.5

- Number read-back is compared by value, so a setting the radio returns with
  leading zeros (Virtual U3S > Set time reads "0020") no longer stops Apply.

#### v0.2.4

- Number and Byte settings now show and enforce the real range reported by the
  radio (for example SSB > USB Audio > Gain and Monitor are 0 to 99, 1-digit
  bytes are 0 to 9) instead of always 0 to 255.
- Table columns can be dragged wider or narrower; hover over a value to see it in full.
- Staged edits now show in the table in orange marked "(pending)", and after
  Apply the table shows the values read back from the radio.
- Text settings (Messages, Callsign, Locator) open a wide editor with a
  character counter.
- Text read-back ignores upper/lower case, so typing "cq" and the radio storing
  "CQ" no longer stops the remaining writes.
