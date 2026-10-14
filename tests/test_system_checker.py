from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.engine import system_checker


class TestPrivilegedOperations(unittest.TestCase):
    def test_package_managed_udev_rules_are_recognized(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.rules"
            package_rules = Path(temp_dir) / "usr/lib/udev/rules.d/99-ds4linux.rules"
            source.write_text("package rules", encoding="utf-8")
            package_rules.parent.mkdir(parents=True)
            package_rules.write_bytes(source.read_bytes())
            with (
                mock.patch.object(system_checker, "UDEVS_RULES_SOURCE", source),
                mock.patch.object(system_checker, "UDEVS_RULES_DEST", Path(temp_dir) / "etc/99-ds4linux.rules"),
                mock.patch.object(system_checker, "UDEVS_RULES_PACKAGE_DEST", package_rules),
                mock.patch.object(
                    system_checker,
                    "UDEVS_RULES_PACKAGE_OVERRIDE",
                    Path(temp_dir) / "etc/99-z-ds4linux.rules",
                ),
            ):
                self.assertTrue(system_checker.is_udev_rules_installed())

    def test_divergent_etc_rule_overrides_and_is_not_hidden_by_package_copy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.rules"
            admin_rule = root / "etc/99-z-ds4linux.rules"
            package_rule = root / "usr/lib/udev/rules.d/99-z-ds4linux.rules"
            source.write_text("current rules", encoding="utf-8")
            admin_rule.parent.mkdir(parents=True)
            package_rule.parent.mkdir(parents=True)
            admin_rule.write_text("old local override", encoding="utf-8")
            package_rule.write_bytes(source.read_bytes())
            with (
                mock.patch.object(system_checker, "UDEVS_RULES_SOURCE", source),
                mock.patch.object(system_checker, "UDEVS_RULES_PACKAGE_OVERRIDE", admin_rule),
                mock.patch.object(system_checker, "UDEVS_RULES_DEST", root / "etc/99-ds4linux.rules"),
                mock.patch.object(system_checker, "UDEVS_RULES_PACKAGE_DEST", package_rule),
            ):
                self.assertFalse(system_checker.is_udev_rules_installed())

    def test_package_rule_runs_after_legacy_local_rule_without_replacing_it(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.rules"
            old_admin_rule = root / "etc/99-ds4linux.rules"
            package_rule = root / "usr/lib/udev/rules.d/99-z-ds4linux.rules"
            source.write_text("current safe rules", encoding="utf-8")
            old_admin_rule.parent.mkdir(parents=True)
            package_rule.parent.mkdir(parents=True)
            old_admin_rule.write_text("legacy broad rule", encoding="utf-8")
            package_rule.write_bytes(source.read_bytes())
            self.assertGreater(package_rule.name, old_admin_rule.name)
            with (
                mock.patch.object(system_checker, "UDEVS_RULES_SOURCE", source),
                mock.patch.object(system_checker, "UDEVS_RULES_DEST", old_admin_rule),
                mock.patch.object(system_checker, "UDEVS_RULES_PACKAGE_DEST", package_rule),
                mock.patch.object(
                    system_checker,
                    "UDEVS_RULES_PACKAGE_OVERRIDE",
                    root / "etc/99-z-ds4linux.rules",
                ),
            ):
                self.assertTrue(system_checker.is_udev_rules_installed())
            self.assertEqual(old_admin_rule.read_text(encoding="utf-8"), "legacy broad rule")

    def test_manual_udev_repair_preserves_existing_local_rule(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.rules"
            local_rule = root / "etc/99-ds4linux.rules"
            source.write_text("current rules", encoding="utf-8")
            local_rule.parent.mkdir(parents=True)
            local_rule.write_text("administrator content", encoding="utf-8")
            with (
                mock.patch.object(system_checker, "UDEVS_RULES_SOURCE", source),
                mock.patch.object(system_checker, "UDEVS_RULES_DEST", local_rule),
                mock.patch.object(system_checker, "UDEVS_RULES_PACKAGE_DEST", root / "missing-package-rule"),
                mock.patch.object(
                    system_checker,
                    "UDEVS_RULES_PACKAGE_OVERRIDE",
                    root / "etc/99-z-ds4linux.rules",
                ),
                mock.patch.object(system_checker, "is_udev_rules_installed", return_value=False),
                mock.patch.object(system_checker, "_run_privileged") as run_privileged,
            ):
                ok, message = system_checker.install_udev_rules()

            self.assertFalse(ok)
            self.assertIn("foi preservada", message)
            self.assertEqual(local_rule.read_text(encoding="utf-8"), "administrator content")
            run_privileged.assert_not_called()

    @mock.patch.object(system_checker, "is_module_loaded", return_value=False)
    @mock.patch.object(system_checker, "is_udev_rules_installed", return_value=False)
    @mock.patch.object(system_checker, "scan_ds4_devices", return_value=[])
    @mock.patch.object(system_checker, "_run_privileged")
    def test_system_readiness_check_is_read_only(self, run_privileged, _scan, _rules, _module):
        ok, messages = system_checker.ensure_system_ready()
        self.assertFalse(ok)
        self.assertTrue(any("Regras udev ausentes" in message for message in messages))
        run_privileged.assert_not_called()

    def test_legacy_credential_is_unlinked_without_reading(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            legacy_file = Path(temp_dir) / ".sudo_pass"
            legacy_file.write_text("must never be read", encoding="utf-8")
            with (
                mock.patch.object(system_checker, "SUDO_PASS_FILE", legacy_file),
                mock.patch.object(Path, "read_text", side_effect=AssertionError("secret read")),
            ):
                self.assertTrue(system_checker.discard_legacy_sudo_secret())
            self.assertFalse(legacy_file.exists())

    def test_missing_legacy_credential_is_a_noop(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch.object(system_checker, "SUDO_PASS_FILE", Path(temp_dir) / "absent"):
                self.assertFalse(system_checker.discard_legacy_sudo_secret())

    @mock.patch.object(system_checker.shutil, "which", return_value="/usr/bin/pkexec")
    @mock.patch.object(system_checker.subprocess, "run")
    def test_privileged_runner_uses_fixed_argv_without_shell_or_password(self, run, _which):
        run.return_value = subprocess.CompletedProcess([], 0, "ok", "")
        result = system_checker._run_privileged("/usr/sbin/modprobe", "hid-playstation")
        self.assertEqual(result, (0, "ok", ""))
        args, kwargs = run.call_args
        self.assertEqual(args[0], ["/usr/bin/pkexec", "/usr/sbin/modprobe", "hid-playstation"])
        self.assertTrue(kwargs["capture_output"])
        self.assertTrue(kwargs["text"])
        self.assertEqual(kwargs["timeout"], 60)
        self.assertNotIn("input", kwargs)
        self.assertNotIn("shell", kwargs)

    @mock.patch.object(system_checker.shutil, "which", return_value=None)
    @mock.patch.object(system_checker.subprocess, "run")
    def test_missing_polkit_agent_returns_actionable_error(self, run, _which):
        code, _stdout, error = system_checker._run_privileged("/usr/sbin/modprobe", "hid-playstation")
        self.assertEqual(code, 127)
        self.assertIn("pkexec", error)
        run.assert_not_called()

    @mock.patch.object(system_checker.shutil, "which", return_value="/usr/bin/pkexec")
    @mock.patch.object(system_checker.subprocess, "run")
    @mock.patch.object(system_checker, "_current_audit_session_id", return_value="2")
    @mock.patch.object(system_checker, "_active_graphical_audit_session_ids", return_value={"788"})
    @mock.patch.object(system_checker, "_user_linger_enabled", return_value=True)
    def test_pkexec_without_agent_reports_stale_graphical_session(
        self, linger_enabled, active_sessions, current_session, run, _which
    ):
        run.return_value = subprocess.CompletedProcess(
            [],
            127,
            "",
            "Error creating textual authentication agent: Error opening current controlling "
            "terminal for the process (/dev/tty): No such device or address",
        )

        code, _stdout, error = system_checker._run_privileged("/usr/bin/udevadm", "trigger")

        self.assertEqual(code, 127)
        self.assertIn("auditoria 2", error)
        self.assertIn("sessão gráfica ativa usa 788", error)
        self.assertIn("linger está habilitado", error)
        self.assertIn("interromper serviços em segundo plano", error)
        self.assertIn("nenhuma alteração foi aplicada", error)
        current_session.assert_called_once_with()
        active_sessions.assert_called_once_with()
        linger_enabled.assert_called_once_with()

    @mock.patch.object(system_checker.shutil, "which", return_value="/usr/bin/loginctl")
    @mock.patch.object(
        system_checker.subprocess,
        "run",
        side_effect=[
            subprocess.CompletedProcess([], 0, "788 1000 servidor seat0 1906117 user tty2 no -\n", ""),
            subprocess.CompletedProcess(
                [], 0, "Active=yes\nAudit=788\nSeat=seat0\nType=wayland\n", ""
            ),
        ],
    )
    def test_active_graphical_audit_session_ids_are_read_from_logind(self, run, _which):
        self.assertEqual(system_checker._active_graphical_audit_session_ids(), {"788"})
        self.assertEqual(run.call_args_list[0].args[0], [
            "/usr/bin/loginctl", "list-sessions", "--no-legend", "--no-pager",
        ])
        self.assertEqual(run.call_args_list[1].args[0], [
            "/usr/bin/loginctl", "show-session", "788", "-p", "Active", "-p", "Audit",
            "-p", "Seat", "-p", "Type",
        ])

    @mock.patch.object(system_checker.shutil, "which", return_value="/usr/bin/pkexec")
    @mock.patch.object(
        system_checker.subprocess,
        "run",
        side_effect=subprocess.TimeoutExpired(cmd="pkexec", timeout=60),
    )
    def test_privileged_timeout_is_reported(self, _run, _which):
        code, _stdout, error = system_checker._run_privileged("/usr/bin/udevadm", "trigger")
        self.assertEqual(code, 124)
        self.assertIn("60 segundos", error)

    @mock.patch.object(system_checker, "_run_privileged")
    @mock.patch.object(system_checker, "is_module_loaded", return_value=False)
    def test_module_name_is_validated_before_privileged_call(self, _loaded, run_privileged):
        self.assertFalse(system_checker.load_module("bad;touch /tmp/injected"))
        run_privileged.assert_not_called()

    @mock.patch.object(system_checker, "_run_privileged", return_value=(0, "", ""))
    @mock.patch.object(system_checker, "is_module_loaded", return_value=False)
    def test_module_load_uses_expected_kernel_operation(self, _loaded, run_privileged):
        self.assertTrue(system_checker.load_module())
        run_privileged.assert_called_once_with("/usr/sbin/modprobe", "hid-playstation")

    def test_udev_install_uses_restricted_install_and_stops_on_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.rules"
            source.write_text("rules", encoding="utf-8")
            destination = Path(temp_dir) / "rules.d" / "99-ds4linux.rules"
            with (
                mock.patch.object(system_checker, "UDEVS_RULES_SOURCE", source),
                mock.patch.object(system_checker, "UDEVS_RULES_DEST", destination),
                mock.patch.object(system_checker, "is_udev_rules_installed", return_value=False),
                mock.patch.object(
                    system_checker,
                    "_run_privileged",
                    side_effect=[(0, "", ""), (1, "", "reload denied")],
                ) as run_privileged,
            ):
                ok, message = system_checker.install_udev_rules()

            self.assertFalse(ok)
            self.assertEqual(message, "reload denied")
            self.assertEqual(run_privileged.call_count, 2)
            self.assertEqual(
                run_privileged.call_args_list[0].args,
                ("/usr/bin/install", "-D", "-m", "0644", "--", str(source), str(destination)),
            )
            self.assertEqual(
                run_privileged.call_args_list[1].args,
                ("/usr/bin/udevadm", "control", "--reload-rules"),
            )


if __name__ == "__main__":
    unittest.main()
