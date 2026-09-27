# Mobile web app and presentation setup

FireAtlas now has an installable **Progressive Web App (PWA)**: a web-app manifest,
home-screen icons, standalone launch, browser installation instructions and an
offline reconnect screen. Open `/install.html` on the running server.

This is the existing responsive application running in an app window. There is
no Android APK or native iOS project. Crew positions, route briefings and alerts
are fictional local exercises; there is no real GPS or cross-device session sync.

## Presenting on a phone

1. Run the Python application behind a trusted HTTPS address reachable from the
   phone, with the intended populated database. The recent global NASA CSVs and
   database are local ignored files, so a fresh Git checkout alone cannot show
   those observations. Import the CSVs or transfer the populated database.
2. Open the address in Chrome on Android or Safari on iPhone.
3. Follow `/install.html` to install/add to the home screen and launch the app.
4. Rehearse rotation, filters, navigation, Crew Device selection and downloads on
   that exact phone. Emulator checks do not replace this step.

For an online preview on a trusted local network:

```bash
uv run python -m fireatlas.web --db data/fireatlas.sqlite3 --host 0.0.0.0 --port 8000
```

Use `http://<laptop-LAN-address>:8000` from the phone. The phone's `localhost`
points to itself. Plain LAN HTTP is suitable for viewing the online responsive
website; use trusted HTTPS for installability and offline service workers.
A public HTTPS deployment has not been provisioned by this update.

## Offline behavior

The globe, calendar and research tools require the application server. Their
API responses are not cached by the root app service worker. Launching these
pages offline shows a reconnect screen instead of stale observation data.

The Training Lab has a separate service worker at the narrower `/training.html`
scope. Open it online and wait for **Offline page ready** and **Progress saved
in this tab**. Advance the clock and choose Crew Bravo, disconnect, then reload
that same tab. The saved exercise and offline export remain available. A fresh
tab does not contain a previous session's briefing.

## Verification

With a local server running:

```bash
uv run --with playwright python scripts/verify_mobile_app.py
```

The check uses a disposable persistent Chrome profile and 390 × 844 touch
emulation. It validates manifest/installability, offline launch, worker scope,
actual offline reload with saved clock/crew, export, and JavaScript exceptions.
All checks passed on 27 September 2026. No physical-phone installation was tested.

The root worker owns only `fireatlas-app-shell-*` caches. The existing Training
Lab worker keeps its independent versioned cache and exercise recovery logic.

References: [MDN installation requirements](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Making_PWAs_installable),
[Apple home-screen instructions](https://support.apple.com/guide/iphone/iphea86e5236/ios).
