# USB Charge Control — iOS 16 (rootless)

**Current version: v0.8.12.** A native UIKit charging-control app by 551UK for supported Dopamine rootless iOS 16 jailbreaks.

[**Download latest DEB and source**](https://github.com/551UK/Charger-Control-iOS16/releases/latest)

## Features

- Adjustable wired USB charging-current cap, 500–2400mA, with one-tap restore.
- Live charger, input-rail and battery telemetry (iOS readings can take 15–20 seconds to refresh).
- Persistent current control and independent safety watchdog.
- One native app only, without the obsolete USB Diagnostics icon.

## What's new in v0.8.12

- Reduced the gap between connection/charger status and the **CHARGING DATA** heading.
- Removed the bottom **Charger Rating is iOS-reported…** paragraph and the **2400mA is a ceiling…** line in the app (the technical safety note remains here in the README).
- Pulled **Enable current limit**, its switch, both buttons and the existing iOS telemetry disclaimer up to eliminate wasted space.
- Retained the current readings, **green Input Rail mA**, blue cap heading and GitHub footer.

## Previously in v0.8.11

- **Input Rail mA** reading highlighted in green at all times, including when data is unavailable. Input Rail title and watts remain white.
- No charging controller, cap, Restore or watchdog changes.

## Previously in v0.8.10

- Shorter home-screen label: **Charge Control**, with Sileo package name **USB Charge Control** unchanged.
- **Charging Data** readings have slightly tighter spacing.
- Replaced the separate battery percentage and USB voltage lines with a single **Charging: Yes | USB Voltage: X.XX V** line.

## Changes retained from v0.8.9

- Centered **USB Charge Control** title.
- Removed the 551UK/Dopamine/iOS subtitle entirely.
- Placed the blue **CHARGING CURRENT CAP** label and selected mA value on one row.
- Right-aligned the 2400mA endpoint label to the right edge of the slider.
- Added a tappable GitHub link at the bottom of the app.
- Renamed the Sileo title to **USB Charge Control** and shortened the package description.

**Charging logic is unchanged from v0.8.8.** This release recompiles the native UI and repackages the unchanged background daemon. On-device testing is required to confirm the new layout.

## Source, builds and backups

- [Browse current source](source/)
- [Release history and downloads](https://github.com/551UK/Charger-Control-iOS16/releases)
- [Source and DEB archive](dist/)
- [Known-good v0.8.4 backup](backups/)

The v0.8.12 source ZIP contains the complete DEB payload, native source, executable and scripts. The GitHub Actions workflow builds the arm64 native app using the iOS SDK, packages the rootless DEB, publishes the release and commits binaries to `dist/`. To reproduce the package from the archive, run `python3 build_usb_v0812.py` on Linux with `dpkg-deb` installed.

**Safety:** 2400mA is a cap ceiling, not a forced charging speed. The app does not spoof temperatures or throttle CPU/GPU. Restoring a software cap does not necessarily instantly change hardware charging behaviour.
