import os
import re
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class PackagingTest(unittest.TestCase):
    def test_dockerfile_copies_every_local_module_app_imports(self):
        with open(os.path.join(ROOT, "app.py")) as f:
            imports = set(re.findall(r"^import (\w+)$", f.read(), re.M))
        localModules = {m for m in imports if os.path.exists(os.path.join(ROOT, m + ".py"))}
        with open(os.path.join(ROOT, "Dockerfile")) as f:
            copied = set(re.findall(r"^COPY /(\w+)\.py ", f.read(), re.M))
        self.assertEqual(localModules - copied, set())

    def test_container_stops_promptly(self):
        # Without an init process, python3 is PID 1, ignores SIGTERM, and every stop waits 10 s.
        with open(os.path.join(ROOT, "Dockerfile")) as f:
            entrypoint = re.search(r"^ENTRYPOINT (.*)$", f.read(), re.M).group(1)
        self.assertTrue(entrypoint.startswith('["/sbin/tini","--"'), entrypoint)

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_config_json_is_git_ignored(self):
        result = subprocess.run(["git", "check-ignore", "-q", "config.json"], cwd=ROOT)
        self.assertEqual(result.returncode, 0, "config.json (holds the Plex token) must be git-ignored")


class NoPersonalDetailsTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_devices_json_is_git_ignored(self):
        result = subprocess.run(["git", "check-ignore", "-q", "devices.json"], cwd=ROOT)
        self.assertEqual(result.returncode, 0, "devices.json (device serials, IDs, signatures) must be git-ignored")

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_only_placeholder_macs_are_committed(self):
        # A real MAC would identify someone's subscription; examples use 00:1A:79:00:00:0X or XX.
        files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
        found = {}
        for name in files:
            try:
                with open(os.path.join(ROOT, name), errors="ignore") as f:
                    text = f.read()
            except OSError:
                continue
            for mac in re.findall(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b", text):
                if not re.match(r"(?i)00[:-]1A[:-]79[:-]00[:-]00[:-]0[0-9]$", mac):
                    found.setdefault(name, set()).add(mac)
        self.assertEqual(found, {})


if __name__ == "__main__":
    unittest.main()
