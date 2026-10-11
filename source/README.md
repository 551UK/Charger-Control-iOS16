# USB Charge Control v0.8.12 — UIKit layout update

A rootless iOS 16/Dopamine native app for adjustable USB charge-current caps and charging power telemetry.

## New in v0.8.12

- Tightens the spacing from charger status to **CHARGING DATA**, preserving room for two-line status messages.
- Removes the explanatory **2400mA is a ceiling…** and **Charger Rating is iOS-reported…** texts from the native app.
- Moves **Enable current limit**, its switch, action buttons and telemetry notice upward; shortens scroll content accordingly.
- Does not alter the charge controller, USB cap, Restore, watchdog or readings.

## Previous v0.8.11 changes

- The Input Rail **mA current value stays green** (including when unavailable). The watts reading and label stay white; font sizes and charging logic do not change.

## Previous v0.8.10 changes

- Home-screen app label is **Charge Control** (package name stays **USB Charge Control**).
- Removed displayed battery percentage; one line now shows **Charging: Yes/No | USB Voltage: X.XX V**.
- Slightly tighter spacing in **Charging Data** without changing font sizes or colours.

## Layout changes retained from v0.8.9

- Centers the **USB Charge Control** header at the top.
- Removes the obsolete `551UK • Dopamine rootless • iOS 16` subtitle completely.
- Keeps **CHARGING CURRENT CAP** blue, with the selected value right-aligned on the same row.
- Aligns the 500mA and 2400mA labels with the left and right ends of the slider, respectively.
- Shows a persistent tappable **GitHub Repository ↗** link at the bottom of the app.
- Uses **USB Charge Control** as the Sileo package title, with a brief package description.

Charging controller, charging watchdog, USB current-limit and restore logic, and the one-app fix from v0.8.8 are unchanged. No new diagnostics UI or additional app is installed.

## Rebuilding

The full release source ZIP includes the complete package `payload/`, UIKit source and compiled arm64 UIKit executable, and the package scripts. To rebuild the DEB on Linux, extract the source ZIP and run `python3 build_usb_v0812.py` (requires `dpkg-deb`). The UIKit executable is built in the repository's macOS GitHub Actions workflow with the Apple iOS SDK. On installation, the existing `postinst` signs it using `ldid`, as for previous versions.

## Safety

Actual power readings may take 15–20 seconds to update as iOS reports telemetry; a changed cap does not imply instant refreshed telemetry. A 2400mA cap is a ceiling, not a request to force faster charging.
