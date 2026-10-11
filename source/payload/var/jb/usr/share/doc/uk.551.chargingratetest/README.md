551UK USB Charge Control v0.8.4 — Native iPhone App (Dopamine rootless, iOS 16)

Restore-without-replug EXPERIMENTAL FIX:
A previous release only cleared the temporary USB maximum. On XS Max this could
restore IOAccessoryUSBCurrentLimit to 2400mA without promptly returning physical
charging input current. The normal Restore button now:
  1. (when active cap tracked) returns the maximum to its original safe current;
  2. clears this tweak's override;
  3. if originally uncapped, refreshes the USB base-current with the *same*
     base value already published by the Lightning controller, then calls Apple's
     matching RestoreUSBCurrentLimitBase API;
  4. logs results and read-only power telemetry at +3s and +12s.

A restored software limit does not guarantee the hardware immediately resumes
full charging. No physical iPhone results available yet. If you already cleared
v0.8.2's override, the Restore button still offers a base-current refresh when
no foreign USB maximum is active. Another owner's active maximum is never removed.

No charging disconnect/reconnect, battery cutoff, fake thermal levels or CPU/GPU throttling.
The cap control stays 500–2400mA. The native app retains three readings:
Charger Rating, Input Rail [W then mA], Battery [W then mA].

Real software source:
- Python service and controller modules in this ZIP
- UIKit source: https://github.com/551UK/Replaced-Screen-Battery/blob/temporary-usb-charge-native-app-build/ios-usb-charge-control/USBChargeControl.m
The unrelated repository's main branch is not changed by this build branch.

0.8.4: Experimental soft power off/on when Restore is pressed in the native app, with a 5-second independent recovery watchdog. No physical cable reattach is guaranteed. Only test on a spare device with battery charge and wall adapter.

v0.8.5 READ-ONLY DIAGNOSTIC: adds timestamped FAST DETECT USB/SMC state traces to existing Copy Diagnostics action. Native binary, cap setting, and software off/on restore logic are byte-for-byte identical to user-confirmed v0.8.4. Open app with cable unplugged, wait 4 seconds, plug in charger, wait 25 seconds, tap Refresh & Copy Diagnostics.


v0.8.6 — immediate charger-connected message: reads the existing fast Port-Lightning registry telemetry in STATE, displays “Charger Connected — Waiting for Power Readings” during the 16–20 second AppleSmartBattery delay. Uses the existing native app status label. No charging current or power control method changed. If Lightning reports disconnected, displays that state. Does not fake input watts/mA. All v0.8.5 read-only timing logs are retained.


v0.8.7 — native interface cleanup: removes on-screen diagnostics, adds permanent small disclaimer that live iOS power telemetry may lag 15–20 seconds, adds current-ceiling explanation, and displays USB controller cap acknowledgment while battery/rail telemetry catches up. The native UIKit executable is freshly compiled for arm64 iOS 16. The separate charging controller, watchdog, cap-setting and software-power-off/on restore paths have NOT changed. Internal safety logs remain available to the daemon for recovery.


v0.8.8 — removes legacy USB Diagnostics home-screen app (ChargingRate.app) from the DEB; unregisters the old bundle before upgrade and after installation; keeps only native Charge Control. No changes to arm64 app executable, USB controller, watchdog, cap/restore logic or telemetry.
