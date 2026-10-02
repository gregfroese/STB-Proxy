import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def inlineScripts(template):
    with open(os.path.join(ROOT, "templates", template)) as f:
        html = f.read()
    scripts = []
    start = html.find("<script>")
    while start != -1:
        end = html.index("</script>", start)
        scripts.append(html[start + len("<script>"):end])
        start = html.find("<script>", end)
    return "\n".join(scripts).replace("{{ url_for('editor_data') }}", "/editor_data")


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TemplateScriptTest(unittest.TestCase):
    def assertValidJavaScript(self, template):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(inlineScripts(template))
        self.addCleanup(os.remove, f.name)
        result = subprocess.run(["node", "--check", f.name], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_editor_script_is_valid_javascript(self):
        self.assertValidJavaScript("editor.html")

    def test_blocks_script_is_valid_javascript(self):
        self.assertValidJavaScript("blocks.html")


if __name__ == "__main__":
    unittest.main()
