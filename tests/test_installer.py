from __future__ import annotations

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
APP_VERSION = re.search(
    r'^__version__ = "([^"]+)"',
    (REPOSITORY / "src" / "__init__.py").read_text(encoding="utf-8"),
    re.MULTILINE,
).group(1)


class TestInstallerSmoke(unittest.TestCase):
    def test_deb_package_is_installable_by_a_package_manager_without_app_setup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "dist"
            subprocess.run(
                [str(REPOSITORY / "packaging/deb/build-deb.sh"), str(output_dir)],
                check=True,
                cwd=REPOSITORY,
                capture_output=True,
                text=True,
            )
            packages = list(output_dir.glob("*.deb"))
            self.assertEqual(len(packages), 1)
            package = packages[0]
            fields = subprocess.check_output(
                ["dpkg-deb", "-f", str(package), "Package", "Version", "Architecture", "Depends"],
                text=True,
            )
            fields = dict(
                (key, value.strip())
                for key, value in (line.split(":", maxsplit=1) for line in fields.splitlines())
                if key
            )
            self.assertEqual(fields["Package"], "ds4linux")
            self.assertEqual(fields["Version"], APP_VERSION)
            self.assertEqual(fields["Architecture"], "all")
            contents = subprocess.check_output(["dpkg-deb", "--contents", str(package)], text=True)
            self.assertTrue(
                contents.splitlines()[0].startswith("drwxr-xr-x root/root"),
                "the package's root directory must not be installed with restrictive staging permissions",
            )
            for dependency in (
                "python3-evdev",
                "python3-pyudev",
                "python3-pyside6.qtwidgets",
                "python3-pyside6.qtnetwork",
                "udev",
            ):
                self.assertIn(dependency, fields["Depends"])

            extracted = Path(temp_dir) / "extracted"
            extracted.mkdir()
            subprocess.run(["dpkg-deb", "-x", str(package), str(extracted)], check=True)
            control_dir = Path(temp_dir) / "control"
            subprocess.run(["dpkg-deb", "-e", str(package), str(control_dir)], check=True)
            for relative in (
                "usr/bin/ds4linux",
                "usr/share/applications/ds4linux.desktop",
                "usr/share/ds4linux/assets/icon.png",
                "usr/share/ds4linux/udev/99-ds4linux.rules",
                "usr/lib/udev/rules.d/99-z-ds4linux.rules",
                "usr/lib/ds4linux/src/main.py",
            ):
                self.assertTrue((extracted / relative).is_file(), relative)

            launcher = (extracted / "usr/bin/ds4linux").read_text(encoding="utf-8")
            self.assertIn("exec /usr/bin/python3 -m src.main", launcher)
            self.assertNotIn("sudo", launcher)
            self.assertNotIn("pkexec", launcher)
            postinst = (control_dir / "postinst").read_text(encoding="utf-8")
            self.assertIn("udevadm control --reload-rules", postinst)
            self.assertNotIn("pkexec", postinst)

    def test_file_install_launcher_icon_and_udev_are_reproducible_in_temp_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            mock_bin = root / "mock-bin"
            mock_bin.mkdir()
            udev_log = root / "udevadm.log"
            udevadm = mock_bin / "udevadm"
            udevadm.write_text(
                '#!/bin/sh\nprintf "%s\\n" "$*" >> "$UDEVADM_LOG"\n',
                encoding="utf-8",
            )
            udevadm.chmod(0o755)

            install_root = root / "opt" / "ds4linux"
            env = os.environ.copy()
            env.update(
                {
                    "DS4LINUX_INSTALL_DIR": str(install_root),
                    "DS4LINUX_BIN_DIR": str(root / "bin"),
                    "DS4LINUX_DESKTOP_DIR": str(root / "applications"),
                    "DS4LINUX_ICON_DIR": str(root / "icons"),
                    "DS4LINUX_UDEV_RULES_DIR": str(root / "rules.d"),
                    "UDEVADM_LOG": str(udev_log),
                    "PATH": f"{mock_bin}:{env['PATH']}",
                }
            )
            script = (
                'source "$1"; install_files; install_udev_rules; '
                "create_launcher; create_desktop_entry; create_icon"
            )
            subprocess.run(
                ["bash", "-c", script, "installer-smoke", str(REPOSITORY / "install.sh")],
                check=True,
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
            )

            for relative in (
                "src/main.py",
                "assets/ds4_controller.png",
                "assets/joystick.png",
                "assets/icon.png",
                "udev/99-ds4linux.rules",
                "README.md",
                "requirements.txt",
            ):
                self.assertTrue((install_root / relative).is_file(), relative)

            installed_rules = root / "rules.d" / "99-ds4linux.rules"
            self.assertEqual(
                installed_rules.read_bytes(),
                (REPOSITORY / "udev/99-ds4linux.rules").read_bytes(),
            )
            self.assertEqual(
                (root / "icons/ds4linux.png").read_bytes(),
                (REPOSITORY / "assets/icon.png").read_bytes(),
            )
            launcher = (root / "bin/ds4linux").read_text(encoding="utf-8")
            self.assertIn(f'cd "{install_root}"', launcher)
            self.assertIn(f'exec "{install_root}/venv/bin/python" -m src.main "$@"', launcher)
            desktop_entry = (root / "applications/ds4linux.desktop").read_text(encoding="utf-8")
            self.assertIn("Icon=ds4linux", desktop_entry)
            self.assertIn("StartupWMClass=DS4Linux", desktop_entry)
            self.assertEqual(
                udev_log.read_text().splitlines(),
                [
                    "control --reload-rules",
                    "trigger --action=add",
                ],
            )

    def test_installer_syntax_and_no_direct_sysfs_permission_changes(self):
        subprocess.run(["bash", "-n", str(REPOSITORY / "install.sh")], check=True)
        script = (REPOSITORY / "install.sh").read_text(encoding="utf-8")
        self.assertNotIn("/sys/class/leds", script)
        self.assertNotIn("chown root:input", script)
        self.assertNotIn("setup_user_permissions", script)

    def test_embedded_and_installed_udev_policies_do_not_allow_world_write(self):
        rules = (REPOSITORY / "udev/99-ds4linux.rules").read_text(encoding="utf-8")
        constants = (REPOSITORY / "src/constants.py").read_text(encoding="utf-8")
        led_controller = (REPOSITORY / "src/engine/led_controller.py").read_text(encoding="utf-8")
        self.assertNotIn('MODE="0666"', rules + constants + led_controller)
        self.assertIn('MODE="0660"', rules)

    def test_bluetooth_uhid_devices_match_without_usb_parent_attributes(self):
        rules = (REPOSITORY / "udev/99-ds4linux.rules").read_text(encoding="utf-8")
        for product in ("09CC", "0BA0", "05C4"):
            hid_parent = f'KERNELS=="0005:054C:{product}.*"'
            self.assertGreaterEqual(
                rules.count(hid_parent),
                2,
                f"Bluetooth product {product} needs separate hidraw and input rules",
            )


if __name__ == "__main__":
    unittest.main()
