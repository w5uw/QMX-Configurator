QMX+ This is a Windows GUI program developed by me Laurance Brungardt W5UW
that allows you to view and edit all the menu settings you would normally
have to access through PUTTY - Make a folder called QMX_Configurator copy
the files from the repository to that folder and then create a desktop ICON
pointing to the QMX_configurator.py file and that's it baby!
Enjoy

## Changes in v0.2.4

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

## Changes in v0.2.5

- Number read-back is compared by value, so a setting the radio returns with
  leading zeros (Virtual U3S > Set time reads "0020") no longer stops Apply.
