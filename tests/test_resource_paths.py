from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src import resource_paths


class TestResourcePaths(unittest.TestCase):
    def test_source_tree_contains_runtime_assets_and_rules(self):
        for relative in (
            ("assets", "ds4_controller.png"),
            ("assets", "joystick.png"),
            ("assets", "icon.png"),
            ("udev", "99-ds4linux.rules"),
        ):
            self.assertTrue(resource_paths.resource_path(*relative).is_file(), relative)

    def test_wheel_data_directory_is_used_outside_source_tree(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            packaged_rules = data_dir / "share/ds4linux/udev/99-ds4linux.rules"
            packaged_rules.parent.mkdir(parents=True)
            packaged_rules.write_text("packaged", encoding="utf-8")
            with (
                mock.patch.object(resource_paths, "_SOURCE_ROOT", data_dir / "empty"),
                mock.patch.object(resource_paths.sysconfig, "get_path", return_value=str(data_dir)),
            ):
                self.assertEqual(
                    resource_paths.resource_path("udev", "99-ds4linux.rules"),
                    packaged_rules,
                )

    def test_debian_package_assets_and_rules_use_system_share_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app_root = root / "usr/lib/ds4linux"
            data_root = root / "usr/share"
            packaged_icon = data_root / "ds4linux/assets/icon.png"
            packaged_rules = data_root / "ds4linux/udev/99-ds4linux.rules"
            packaged_icon.parent.mkdir(parents=True)
            packaged_rules.parent.mkdir(parents=True)
            packaged_icon.write_bytes(b"icon")
            packaged_rules.write_bytes(b"udev")
            with (
                mock.patch.object(resource_paths, "_SOURCE_ROOT", app_root),
                mock.patch.object(resource_paths.sysconfig, "get_path", return_value=str(data_root.parent)),
            ):
                self.assertEqual(resource_paths.resource_path("assets", "icon.png"), packaged_icon)
                self.assertEqual(
                    resource_paths.resource_path("udev", "99-ds4linux.rules"), packaged_rules
                )

    def test_resource_path_rejects_parent_traversal(self):
        with self.assertRaises(ValueError):
            resource_paths.resource_path("assets", "..", "secret")


if __name__ == "__main__":
    unittest.main()
