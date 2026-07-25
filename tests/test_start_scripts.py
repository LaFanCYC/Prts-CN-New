import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class StartScriptTest(unittest.TestCase):
    def test_linux_releases_port_and_opens_url(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "start_linux.sh"
            shutil.copy(ROOT / "start_linux.sh", script)
            script.chmod(0o755)

            bin_dir = root / "bin"
            python_dir = root / ".venv" / "bin"
            log_dir = root / "logs"
            bin_dir.mkdir()
            python_dir.mkdir(parents=True)
            log_dir.mkdir()

            self._write_executable(
                bin_dir / "fuser",
                '#!/bin/sh\nprintf "%s\\n" "$*" >> "$TEST_LOG/fuser"\nexit 0\n',
            )
            self._write_executable(
                bin_dir / "xdg-open",
                '#!/bin/sh\nprintf "%s\\n" "$1" > "$TEST_LOG/browser"\n',
            )
            self._write_executable(
                python_dir / "python",
                '#!/bin/sh\nprintf "%s\\n" "$*" > "$TEST_LOG/python"\nsleep 2\n',
            )

            environment = os.environ.copy()
            environment.update(
                {
                    "CAMPUS_HOST": "127.0.0.1",
                    "CAMPUS_PORT": "43210",
                    "PATH": f"{bin_dir}:{environment['PATH']}",
                    "TEST_LOG": str(log_dir),
                }
            )
            result = subprocess.run(
                [str(script)],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=5,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("-k 43210/tcp", self._read_log(log_dir / "fuser"))
            self.assertEqual(
                (log_dir / "browser").read_text().strip(),
                "http://127.0.0.1:43210",
            )
            self.assertIn(
                "-m waitress --host=127.0.0.1 --port=43210 --call app:create_app",
                (log_dir / "python").read_text(),
            )

    @staticmethod
    def _write_executable(path, content):
        path.write_text(content)
        path.chmod(0o755)

    @staticmethod
    def _read_log(path):
        return path.read_text() if path.exists() else ""


if __name__ == "__main__":
    unittest.main()
