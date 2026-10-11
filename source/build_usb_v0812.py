"""Repackage the complete extracted v0.8.12 source ZIP into its rootless DEB.

Requires dpkg-deb. The ZIP includes the compiled native UIKit app and preserved
charging helper; no compiler is required to repackage it.
"""
from pathlib import Path
import subprocess
import tempfile
import shutil

root = Path(__file__).resolve().parent
payload = root / 'payload'
output = root / '551UK-USB-Charge-Control-v0.8.12.deb'
assert (payload / 'DEBIAN/control').is_file()
assert (payload / 'var/jb/Applications/USBChargeControl.app/USBChargeControl').is_file()
assert not (payload / 'var/jb/Applications/ChargingRate.app').exists()
with tempfile.TemporaryDirectory() as temp:
    staging = Path(temp) / 'staging'
    shutil.copytree(payload, staging)
    subprocess.run(['dpkg-deb', '--build', '--root-owner-group', str(staging), str(output)], check=True)
print(output)
