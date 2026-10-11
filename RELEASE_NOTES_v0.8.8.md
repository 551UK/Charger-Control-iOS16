# Charge Control v0.8.8 — One-App Packaging Fix

**For jailbroken iOS 16 rootless (Dopamine).**

This is a packaging-only update based on v0.8.7: the native Charge Control executable and charging logic remain unchanged. The legacy **USB Diagnostics** app and its home-screen registration have been removed, leaving only **Charge Control**.

## Included

- Native Charge Control app with adjustable wired current cap (500–2400 mA).
- Charger/input/battery data, live cap feedback and iOS telemetry-delay notice.
- Persistent cap, background watchdog and restoration controls.
- No temperature spoofing or CPU/GPU throttling.

**Upgrading:** Install the v0.8.8 DEB directly over v0.8.7 using Sileo. Do not uninstall the working Charge Control app first. If the old icon persists after installation, respring or refresh the icon cache.

**Testing:** Charging control was confirmed working on v0.8.7; v0.8.8 only changes packaging, and still needs on-device confirmation that old icon cleanup works.

**Files:** `.deb` installable package; `-Source.zip` complete source and packaging payload. Archived known-good v0.8.4 remains in `backups/`.
