# 551UK USB Charge Control — iOS 16 rootless

Native Charge Control app for jailbroken iOS 16 (Dopamine rootless), developed by **551UK**.

## Current build: v0.8.8

Version 0.8.8 is a **packaging-only update** based on the functional v0.8.7 build. It removes the obsolete **USB Diagnostics** home-screen app and keeps only **Charge Control**. The native Charge Control executable and core charging code are preserved from v0.8.7.

### Features

- Configurable wired USB charge-current cap, from 500 to 2400 mA (hardware/current availability dependent).
- Connection and applied-cap feedback, and live readings for charger/input/battery power.
- Persistent cap management, background recovery watchdog and safe restore behavior.
- An in-app disclaimer that iOS charging telemetry can lag behind a newly applied setting.
- No CPU/GPU throttling or temperature spoofing.

> **Important:** Live iOS charge telemetry may take time to refresh. Setting a cap is not proof that every live current reading will immediately change. This modifies low-level charging behaviour: use responsibly and monitor the device.
## Install

Get the latest `.deb` from [Releases](https://github.com/551UK/Charger-Control-iOS16/releases) and install it using Sileo on an eligible rootless jailbreak. Install directly over v0.8.7; do not uninstall the working app first. Dependencies: `python3` and `ldid` as indicated by the DEB package.

If the legacy USB Diagnostics icon lingers after upgrading, refresh the icon cache or respring.

## Source and reproducible packaging

The [source/](source/) directory contains browsable UIKit and Python source, installation scripts and supporting configuration. The **complete original payload**, including compiled executables and icons, is included in [the v0.8.8 source ZIP](dist/551UK-USB-Charge-Control-v0.8.8-Source.zip). To reproduce the DEB, extract that ZIP into a working directory and run `python3 build_usb_v088.py` there (requires `dpkg-deb`). No native recompilation is needed for this packaging-only update.

The latest v0.8.8 DEB and complete ZIP are also mirrored under [dist/](dist/). The known-good v0.8.4 backup is preserved separately under [backups/](backups/).

## Version history

- **v0.8.8** — Removes duplicate USB Diagnostics app; charging logic unchanged from v0.8.7.
- **v0.8.7** — Native app and updated feedback/telemetry UI.
- **v0.8.4** — Saved as a known-good backup for recovery.

Maintained by 551UK.
