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

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_config_json_is_git_ignored(self):
        result = subprocess.run(["git", "check-ignore", "-q", "config.json"], cwd=ROOT)
        self.assertEqual(result.returncode, 0, "config.json (holds the Plex token) must be git-ignored")


if __name__ == "__main__":
    unittest.main()
