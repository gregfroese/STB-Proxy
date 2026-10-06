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

    def test_guide_script_is_valid_javascript(self):
        self.assertValidJavaScript("guide.html")

    def test_player_script_is_valid_javascript(self):
        self.assertValidJavaScript("_player.html")


class PreviewPromptTest(unittest.TestCase):
    def setUp(self):
        self.script = inlineScripts("_player.html")
        with open(os.path.join(ROOT, "templates", "_player.html")) as f:
            self.html = f.read()

    def test_failed_preview_offers_retry_not_just_dead(self):
        # A busy portal (503 from /play) looks the same to the browser as a dead stream.
        self.assertIn('id="retryPreview"', self.html)
        self.assertIn("function retryPreview", self.script)
        self.assertIn("busy", self.html)

    def test_player_does_not_block_the_page(self):
        # A docked panel, not a modal, so the guide and editor stay usable while it plays.
        self.assertNotIn("modal", self.html)
        self.assertIn('id="playerPanel"', self.html)

    def test_closing_the_player_drops_the_stream(self):
        self.assertRegex(self.script, r'function stopStream\(\) \{[^}]*player\.removeAttribute\("src"\);\s*player\.load\(\);')
        self.assertRegex(self.script, r'function closePlayer\(\) \{[^}]*stopStream\(\);')

    def test_switching_channels_lets_the_last_stream_close_first(self):
        # Otherwise the new stream finds the portal connection busy ("No free MAC").
        self.assertRegex(self.script, r'function selectChannel\(ele\) \{[\s\S]*?stopStream\(\);[\s\S]*?startStream\(wasPlaying \? \d+ : 0\);[\s\S]*?\n    \}')

    def test_failed_preview_retries_once_before_offering_mark_dead(self):
        self.assertRegex(self.script, r'if \(!retried\) \{[^}]*startStream\(\d+\);\s*return;')

    def test_preview_failure_tolerates_missing_row(self):
        self.assertRegex(self.script, r"var row = rowFor\(currentChannel\);\s*if \(!row \|\| row\.dead\)")


if __name__ == "__main__":
    unittest.main()
