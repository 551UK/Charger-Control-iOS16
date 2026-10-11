# 551UK USB Charge Control — iOS 16 rootless

Native Charge Control app for jailbroken iOS 16 (Dopamine rootless)

### Features

- Configurable wired USB charge-current cap, from 500 to 2400 mA (hardware/current availability dependent).
- Connection and applied-cap feedback, and live readings for charger/input/battery power.
- Persistent cap management, background recovery watchdog and safe restore behavior.
- An in-app disclaimer that iOS charging telemetry can lag behind a newly applied setting.
- No CPU/GPU throttling or temperature spoofing.

> **Important:** Live iOS charge telemetry may take time to refresh. Setting a cap is not proof that every live current reading will immediately change. This modifies low-level charging behaviour: use responsibly and monitor the device.

