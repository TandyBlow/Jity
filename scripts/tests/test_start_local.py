"""Exercise launcher decisions without starting the real development servers."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


LAUNCHER = Path(__file__).resolve().parents[1] / "start_local.sh"


class StartLocalTests(unittest.TestCase):
    def run_launcher(self, busy_ports, backend_port="8000", frontend_port="3000"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / "scripts"
            scripts.mkdir()
            shutil.copy2(LAUNCHER, scripts / "start_local.sh")
            bin_dir = root / "bin"
            bin_dir.mkdir()
            lsof = bin_dir / "lsof"
            lsof.write_text(
                '#!/usr/bin/env bash\n'
                'for arg in "$@"; do\n'
                '  case "$arg" in\n'
                '    -iTCP:*) port="${arg#-iTCP:}" ;;\n'
                '  esac\n'
                'done\n'
                '[[ ",${MOCK_BUSY_PORTS}," == *",${port},"* ]]\n'
            )
            lsof.chmod(0o755)
            logs = root / ".local" / "logs"
            logs.mkdir(parents=True)
            for service in ("backend", "frontend"):
                starter = scripts / f"start_{service}.sh"
                starter.write_text(
                    '#!/usr/bin/env bash\n'
                    f'touch "${{TEST_ROOT}}/{service}.started"\n'
                    'exit 7\n'
                )
                starter.chmod(0o755)
                (logs / f"{service}.log").write_text("existing log\n")
            env = {
                **os.environ,
                "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                "TEST_ROOT": str(root),
                "MOCK_BUSY_PORTS": ",".join(busy_ports),
                "JITY_BACKEND_PORT": backend_port,
                "JITY_FRONTEND_PORT": frontend_port,
            }
            result = subprocess.run(
                ["bash", str(scripts / "start_local.sh")],
                env=env, capture_output=True, text=True, timeout=10,
            )
            started = {
                service for service in ("backend", "frontend")
                if (root / f"{service}.started").exists()
            }
            for service, port in (("backend", backend_port), ("frontend", frontend_port)):
                if port in busy_ports:
                    self.assertEqual((logs / f"{service}.log").read_text(), "existing log\n")
            return result, started

    def test_both_occupied_exits_without_starting_or_truncating_logs(self):
        result, started = self.run_launcher(["8000", "3000"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(started, set())
        self.assertIn("nothing started", result.stdout)

    def test_existing_frontend_only_starts_backend(self):
        result, started = self.run_launcher(["3000"])
        self.assertEqual(started, {"backend"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("Backend process exited", result.stdout)

    def test_existing_backend_only_starts_frontend(self):
        result, started = self.run_launcher(["8000"])
        self.assertEqual(started, {"frontend"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("Frontend process exited", result.stdout)

    def test_empty_ports_start_both_and_report_child_exit(self):
        result, started = self.run_launcher([])
        self.assertEqual(started, {"backend", "frontend"})
        self.assertEqual(result.returncode, 1)

    def test_custom_ports_are_checked(self):
        result, started = self.run_launcher(["8100", "3100"], "8100", "3100")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(started, set())


if __name__ == "__main__":
    unittest.main()
