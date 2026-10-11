# USB Charge Control — iOS 16 (rootless)

**Current version: v0.8.18.** A native UIKit charging-control app by 551UK for supported Dopamine rootless iOS 16 jailbreaks.

[**Download latest DEB and source**](https://github.com/551UK/Charger-Control-iOS16/releases/latest)

## Features

- Adjustable wired USB charging-current cap, 500–2400mA, with one-tap restore.
- Live charger, input-rail and battery telemetry (iOS readings can take 15–20 seconds to refresh).
- Persistent current control and independent safety watchdog.
- One native app only, without the obsolete USB Diagnostics icon.

## What's new in v0.8.18

- Centered the shared charger status text area so **Charger Disconnected**, **Charger Connected**, cap-applied, restore, waiting, offline and error messages are horizontally centred.
- Status colours, position, dimensions, line wrapping, live updates and charging functionality are unchanged.

## Previously in v0.8.17

- Simplified the in-app telemetry notice: **Live power readings and the displayed USB current cap may take 15–20 seconds to update while iOS telemetry catches up.**
- Removed the statement that USB cap confirmation is separate from the live readings.
- No changes to the UI layout, readings, current-limit controls, daemon or watchdog.

## Previously in v0.8.16

- Made both blue section headings **CHARGING DATA** and **CHARGING CURRENT CAP** identical **15 pt semibold** headings.
- Kept the original blue colour, both 20-point section gaps, and the selected mA value on the same line.
- Preserved all readings, green Input Rail mA and charging controls.

## Previously in v0.8.15

- Moved the centered USB Charge Control title down 8 points.
- Increased the gaps above both blue section headings to 20 points.
- Cleaned main of stale workflows, duplicate readmes and scripts. Keeps the complete latest source ZIP, only the latest DEB, core project files and the known-good v0.8.4 backup.

## Previously in v0.8.14

- Swapped the final two rows in **CHARGING DATA**: **Effective USB current cap** is directly above **Charging | USB Voltage**.
- Standardised all five Charging Data values to **16 pt medium-weight, white text**, keeping only the **Input Rail mA value green**.
- Increased the gap above each blue section heading from **8 pt to 14 pt**, retaining the compact overall layout.

## Previously in v0.8.13

- **Charger Connected** and successful **mA cap applied** controller statuses are green during live refreshes; disconnection and errors remain red.
- Centered title lowered by four points.
- Equal compact spacing around the **CHARGING DATA** and **CHARGING CURRENT CAP** blue section headings.
- GitHub release has no description. Only the newest DEB is kept in `dist/` and earlier release DEB assets are removed, while Git history retains older source and the known-good backup remains intact.

## Previously in v0.8.12

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

The v0.8.18 source ZIP contains the complete DEB payload, native source, executable and scripts. The GitHub Actions workflow builds the arm64 native app using the iOS SDK, packages the rootless DEB, publishes the release and commits binaries to `dist/`. To reproduce the package from the archive, run `python3 build_usb.py` on Linux with `dpkg-deb` installed.

**Safety:** 2400mA is a cap ceiling, not a forced charging speed. The app does not spoof temperatures or throttle CPU/GPU. Restoring a software cap does not necessarily instantly change hardware charging behaviour.
