QMX+ This is a Windows GUI program developed by me Laurance Brungardt W5UW
that allows you to view and edit all the menu settings you would normally
have to access through PUTTY - Make a folder called QMX_Configurator copy
the files from the repository to that folder and then create a desktop ICON
pointing to the QMX_configurator.py file and that's it baby!
Enjoy

## Release notes

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

Still read-only: PA Voltage and Max. PA voltage (decimal format not yet
supported), calibration, mask fields, actions, and the Delimiter and GPS NMEA
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
