# 551UK USB Charge Control v0.8.8 — ONE APP

v0.8.8 is a packaging-only fix to v0.8.7. It removes the legacy `USB Diagnostics` app (`/var/jb/Applications/ChargingRate.app`, bundle ID `uk.551.chargingratetest`) and its stale home-screen registration. It retains the native `Charge Control` UIKit app (`/var/jb/Applications/USBChargeControl.app`, bundle ID `uk.551.usbchargecontrol`).

**No edits to the native app binary, native app source, charging daemon, backend Python source, background watchdog, power restore, cap handling, or telemetry.** The embedded native executable is exactly the v0.8.7 working binary; only the Info.plist version has been updated. The new package still uses package ID `uk.551.chargingratetest`, which is distinct from the removed UI's app bundle identifier but deliberately unchanged for seamless upgrading and retained settings.

Upgrading via Sileo should replace 0.8.7 directly and unregister/remove the obsolete home-screen icon. If the old icon remains cached, refresh the icon cache (`uicache -a`) or respring.

The `payload/` directory contains all files for reproduction and all maintainer scripts. Rebuild on Linux using `python3 build_usb_v088.py` (requires dpkg-deb). The source `.m` is bundled for reference; no recompilation is needed as this release does not alter the executable.

Known good v0.8.4 backup is still preserved in ChatGPT Library: `/551UK USB Charge Control/Known Good v0.8.4/`.
