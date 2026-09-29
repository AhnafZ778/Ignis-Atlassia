# Mobile web app and presentation setup

FireAtlas has an installable **Progressive Web App (PWA)** with a web-app manifest,
home-screen icons, standalone launch, browser installation instructions and an
offline reconnect screen. Open `/install.html` on the running server.

This is the responsive website running in an app window. There is no Android APK
or native iOS project.

## Presenting on a phone

1. Run the Python application behind a trusted HTTPS address reachable from the
   phone, with the intended populated database. Local NASA CSVs and databases
   are not included in a fresh Git checkout.
2. Open the address in Chrome on Android or Safari on iPhone.
3. Follow `/install.html` to install/add to the home screen and launch FireAtlas.
4. Rehearse map navigation, calendar controls and downloads on that exact phone.

For an online preview on a trusted local network:

```bash
uv run python -m fireatlas.web --db data/fireatlas.sqlite3 --host 0.0.0.0 --port 8000
```

Use `http://<laptop-LAN-address>:8000` from the phone. The phone's `localhost`
points to itself. Plain LAN HTTP is suitable for viewing the responsive website;
use trusted HTTPS for installability and service workers. A public HTTPS deployment
has not been provisioned.

## Offline behavior

The globe, calendar and research tools require the application server. Imported
observations are not cached by the root app service worker. Use the offline page
to return to the application when the server is unavailable.

## Verification

With a local server running:

```bash
uv run --with playwright python scripts/verify_mobile_app.py
```

The check uses a disposable Chrome profile and 390 × 844 touch emulation to
validate the app manifest, installation metadata and cached offline page. It does
not replace a physical-phone test.

References: [MDN installation requirements](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Making_PWAs_installable),
[Apple home-screen instructions](https://support.apple.com/guide/iphone/iphea86e5236/ios).
