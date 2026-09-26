# AccessTrace demos

The fixed and broken contact forms are ordinary HTML pages with nearby CSS and
JavaScript files. Open either `index.html` through the AccessTrace server or
choose its folder in the app's local page picker. They use fictional data only.

- `fixed/` lets a keyboard user submit the form and reach the visible confirmation.
- `broken/` deliberately has multiple keyboard-accessibility defects: Tab skips the
  required Message field, an empty button has no accessible name, and keyboard
  activation of Submit is blocked. These defects are fixtures for exercising
  AccessTrace; the page uses fictional data only.
