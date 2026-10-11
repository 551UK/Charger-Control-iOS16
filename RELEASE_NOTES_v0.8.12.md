# USB Charge Control v0.8.12

Compact-layout update for Dopamine rootless iOS 16.

- Decreased vertical space between the charge connection status (including `Charger disconnected`) and **CHARGING DATA**.
- Removed the two unnecessary explanations: **2400mA is a ceiling…** and **Charger Rating is iOS-reported…**.
- Moved **Enable current limit**, toggle, both action buttons and telemetry-delay text upwards.
- Preserved the green **Input Rail mA**, one-line **Charging | USB Voltage**, cyan **CHARGING CURRENT CAP**, aligned slider endpoints, app naming and GitHub link.

**No change to charging controls or daemon.** The brief iOS telemetry-delay notice is intentionally retained.

Install over v0.8.11 using Sileo. A respring may be needed for UI cache changes.
