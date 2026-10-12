"""State-machine regression tests. No iPhone or iOS private frameworks needed."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "usb_control_panel", ROOT / "source/usb_control_panel.py"
)
panel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(panel)


class SavedCapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.patches = []
        for name, value in (
            ("PRIVATE", self.root),
            ("REQUESTED", self.root / "requested-cap.json"),
            ("STATE", self.root / "active.json"),
            ("OPLOCK", self.root / "operation.lock"),
            ("_LAST_ERROR", ""),
        ):
            p = mock.patch.object(panel, name, value)
            p.start()
            self.addCleanup(p.stop)
        panel.OPLOCK.touch()

    def test_saved_value_survives_disconnection_and_remains_until_restore(self):
        panel.save_requested_cap(1200)
        self.assertEqual(panel.requested_cap(), 1200)
        panel.save_requested_cap(1800)
        self.assertEqual(panel.requested_cap(), 1800)
        unplugged = {"plugged": 0, "lightning_usb_type": 0,
                     "lightning_usb_power": 0, "usb_max_ma": None}
        with mock.patch.object(panel, "snapshot", return_value=unplugged):
            with mock.patch.object(panel, "do_enable") as enable:
                panel.monitor_once()
                enable.assert_not_called()
            result = panel.do_restore("native-app-or-package-removal")
        self.assertTrue(result["ok"])
        self.assertIsNone(panel.requested_cap())

    def test_saved_cap_auto_reapplies_to_a_charging_cable(self):
        panel.save_requested_cap(1200)
        plugged = {"plugged": 1, "charging": 1, "usb_max_ma": None}
        with mock.patch.object(panel, "snapshot", return_value=plugged):
            with mock.patch.object(panel, "do_enable",
                                   return_value={"ok": True, "message": "applied"}) as apply:
                panel.monitor_once()
        apply.assert_called_once_with(1200, remember=False)
        self.assertEqual(panel.requested_cap(), 1200)

    def test_cap_is_not_applied_to_disconnected_or_idle_input(self):
        panel.save_requested_cap(1600)
        with mock.patch.object(panel, "do_enable") as apply:
            for state in (
                {"plugged": 0, "charging": 0, "lightning_usb_type": 0,
                 "lightning_usb_power": 0, "usb_max_ma": None},
                {"plugged": 1, "charging": 0, "usb_max_ma": None},
            ):
                with mock.patch.object(panel, "snapshot", return_value=state):
                    panel.monitor_once()
            apply.assert_not_called()

    def test_repeated_poll_keeps_an_already_applied_cap(self):
        panel.save_requested_cap(1500)
        panel.write_state({"session": "abc", "original_max": None, "limit_ma": 1500})
        plugged = {"plugged": 1, "charging": 1, "usb_max_ma": 1500}
        with mock.patch.object(panel, "snapshot", return_value=plugged):
            with mock.patch.object(panel, "do_enable") as apply:
                panel.monitor_once()
                apply.assert_not_called()

    def test_unplug_drops_stale_session_but_preserves_user_choice(self):
        panel.save_requested_cap(1700)
        panel.write_state({"session": "abc", "original_max": None, "limit_ma": 1700})
        unplugged = {"plugged": 0, "lightning_usb_type": 0,
                     "lightning_usb_power": 0, "usb_max_ma": None}
        with mock.patch.object(panel, "snapshot", return_value=unplugged):
            panel.monitor_once()
        self.assertIsNone(panel.read_state())
        self.assertEqual(panel.requested_cap(), 1700)

    def test_unowned_usb_max_is_never_overwritten(self):
        panel.save_requested_cap(1200)
        plugged = {"plugged": 1, "charging": 1, "usb_max_ma": 900}
        with mock.patch.object(panel, "snapshot", return_value=plugged):
            with mock.patch.object(panel, "do_enable") as apply:
                panel.monitor_once()
                apply.assert_not_called()

    def test_stale_auto_apply_never_overrides_restore(self):
        # A monitor iteration may have read a cap before the user disabled it.
        # The actual write path must re-check the preference under its lock.
        with mock.patch.object(panel, "CORE", None):
            result = panel.do_enable(1200, remember=False)
        self.assertFalse(result["ok"])
        self.assertIn("cancelled", result["message"])
        self.assertIsNone(panel.read_state())

    def test_successful_manual_enable_remembers_only_verified_cap(self):
        class FakeIO:
            maximum = None
            def context(self):return (object(), object())
            def read(self,acc):
                return {"IsCharging": 1, "ExternalConnected": 1,
                        "IOAccessoryUSBCurrentLimit": 2000,
                        "IOAccessoryUSBCurrentLimitBase": 2000,
                        "IOAccessoryUSBCurrentLimitMaximum": None}
            def field(self,acc,name):
                if name == "IOAccessoryUSBCurrentLimitMaximum":
                    return self.maximum
                if name == "IOAccessoryUSBCurrentLimit":
                    return min(2000, self.maximum or 2000)
                return 2000
            def setmax(self,conn,ma):
                self.maximum = ma
                return 0
            def close(self,conn):pass
            def release(self,acc):pass
        class FakeCore:
            __file__ = "/var/jb/usr/libexec/551uk-usb-currentd.py"
            def __init__(self):self.api=FakeIO()
            def IO(self):return self.api
            def fmt(self,reading):return str(reading)
            def valid_prior(self,value):return isinstance(value,int) and value>0
            def append(self,message):pass
        fake=FakeCore()
        with mock.patch.object(panel, "CORE", fake):
            with mock.patch.object(panel.subprocess, "Popen") as popen:
                popen.return_value.pid = 123
                with mock.patch.object(panel.time, "sleep"):
                    result = panel.do_enable(1400)
        self.assertTrue(result["ok"], result)
        self.assertEqual(panel.requested_cap(), 1400)
        self.assertEqual(panel.read_state()["limit_ma"], 1400)
        self.assertEqual(fake.api.maximum, 1400)

    def test_upgrade_recovery_does_not_clear_saved_value(self):
        panel.save_requested_cap(1300)
        with mock.patch.object(panel, "_restore_locked",
                               return_value={"ok": True, "message": "restored"}) as restore:
            result = panel.do_restore("package-upgrade")
        self.assertTrue(result["ok"])
        restore.assert_called_once_with("package-upgrade")
        self.assertEqual(panel.requested_cap(), 1300)


if __name__ == "__main__":
    unittest.main()
