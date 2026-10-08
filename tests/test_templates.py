import os
import re
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
    return re.sub(r"\{\{ url_for\('(\w+)'\) \}\}", r"/\1", "\n".join(scripts))


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

    def test_portals_script_is_valid_javascript(self):
        self.assertValidJavaScript("portals.html")

    def test_dashboard_script_is_valid_javascript(self):
        self.assertValidJavaScript("dashboard.html")

    def test_guide_script_is_valid_javascript(self):
        self.assertValidJavaScript("guide.html")

    def test_player_script_is_valid_javascript(self):
        self.assertValidJavaScript("_player.html")

    def test_multiview_script_is_valid_javascript(self):
        self.assertValidJavaScript("multiview.html")

    def test_multiview_helpers_are_valid_javascript(self):
        result = subprocess.run(["node", "--check", os.path.join(ROOT, "static", "multiview.js")],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


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
        panel = self.html.split('id="playerPanel"')[1].split('<!-- One channel')[0]
        self.assertNotIn("modal", panel)
        self.assertNotIn("modal", self.script.split("function playChannel")[1].split("\n    }\n")[0])

    def test_closing_the_player_drops_the_stream(self):
        self.assertRegex(self.script, r'function stopStream\(\) \{[^}]*player\.removeAttribute\("src"\);\s*player\.load\(\);')
        self.assertRegex(self.script, r'function closePlayer\(\) \{[\s\S]*?stopStream\(\);[\s\S]*?\n    \}')

    def test_switching_channels_starts_the_next_stream_at_once(self):
        # The server stops this viewer's last preview itself (see stopPreview), so no waiting.
        self.assertRegex(self.script, r'function selectChannel\(ele\) \{[\s\S]*?stopStream\(\);[\s\S]*?startStream\(0\);[\s\S]*?\n    \}')

    def test_failed_preview_retries_once_before_offering_mark_dead(self):
        self.assertRegex(self.script, r'if \(!retried\) \{[^}]*startStream\(\d+\);\s*return;')

    def test_player_has_channel_up_and_down(self):
        self.assertIn('onclick="changeChannel(1)"', self.html)
        self.assertIn('onclick="changeChannel(-1)"', self.html)
        self.assertIn('"PageUp"', self.script)

    def test_channel_that_left_the_list_continues_from_its_place(self):
        self.assertRegex(self.script, r"index == -1 \? \(step > 0 \? lastListIndex : lastListIndex - 1\)")

    def test_lists_can_mark_dead_without_playing(self):
        self.assertIn("function deadToggle", self.script)
        self.assertIn("function deadClicked", self.script)
        for template in ("editor.html", "blocks.html", "guide.html"):
            self.assertIn("deadToggle(", inlineScripts(template), template)

    def test_every_list_is_navigable(self):
        self.assertIn("function channelList", inlineScripts("editor.html"))
        for template in ("blocks.html", "guide.html"):
            with open(os.path.join(ROOT, "templates", template)) as f:
                self.assertIn("channel-list", f.read(), template)

    def test_editor_can_hide_channels_in_blocks(self):
        self.assertIn("hideInBlocks || !rowData.blocks.length", inlineScripts("editor.html"))

    def test_full_screen_keeps_the_controls(self):
        # The whole panel goes full screen, so its channel, block and dead controls float over the video.
        self.assertIn("(panel.requestFullscreen || panel.webkitRequestFullscreen).call(panel)", self.script)
        self.assertIn('controlslist="nofullscreen"', self.html)
        self.assertIn(".player-panel.fullscreen .player-controls", self.html)
        self.assertIn('id="fullscreenButton"', self.html)

    def test_channel_guide_in_player_and_lists(self):
        self.assertIn('id="nowShowing"', self.html)
        self.assertIn('onclick="togglePlayerGuide()"', self.html)
        self.assertIn(".player-panel.fullscreen .player-guide", self.html)
        for template in ("editor.html", "blocks.html", "guide.html"):
            self.assertIn("guideButton(", inlineScripts(template), template)

    def test_preview_failure_tolerates_missing_row(self):
        self.assertRegex(self.script, r"var row = rowFor\(currentChannel\);\s*if \(!row \|\| row\.dead\)")


if __name__ == "__main__":
    unittest.main()
