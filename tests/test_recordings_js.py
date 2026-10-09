import json
import os
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "static", "recordings.js")


@unittest.skipUnless(shutil.which("node"), "node not installed")
class RecordingsScriptTest(unittest.TestCase):
    def run_js(self, body):
        script = "const r = require(%s); console.log(JSON.stringify((() => { %s })()));" % (json.dumps(SCRIPT), body)
        return json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)

    def test_sizes_and_durations_read_naturally(self):
        self.assertEqual(self.run_js("return [0, 900, 1536 * 1024, 3.5 * 1024 ** 3].map(r.formatSize);"),
                         ["0 KB", "1 KB", "1.5 MB", "3.5 GB"])
        self.assertEqual(self.run_js("return [0, 59, 61, 3600, 5430].map(r.formatDuration);"),
                         ["0:00", "0:59", "1:01", "1:00:00", "1:30:30"])

    def test_record_options_offer_the_programme_on_now(self):
        options = self.run_js("return r.recordOptions(1000, {title: 'Game', stop: 4600});")
        self.assertEqual([o["label"] for o in options],
                         ["Until I stop it", "Until Game ends", "30 minutes", "1 hour", "2 hours"])
        self.assertEqual((options[1]["until"], options[2]["minutes"]), (4600, 30))
        self.assertEqual(len(self.run_js("return r.recordOptions(1000, {title: 'Over', stop: 900});")), 4)
        self.assertEqual(len(self.run_js("return r.recordOptions(1000, null);")), 4)

    def test_which_channels_are_recording(self):
        recs = [{"id": "a", "portal": "p1", "channelId": "2", "status": "recording"},
                {"id": "b", "portal": "p1", "channelId": "3", "status": "done"}]
        self.assertEqual(self.run_js("return r.recordingChannels(%s);" % json.dumps(recs)), {"p1/2": "a"})

    def test_recordings_by_channel_know_when_they_started(self):
        recs = [{"id": "a", "portal": "p1", "channelId": "2", "status": "recording", "start": 100},
                {"id": "b", "portal": "p1", "channelId": "3", "status": "done", "start": 50}]
        self.assertEqual(self.run_js("return r.recordingsByChannel(%s);" % json.dumps(recs)), {"p1/2": {"id": "a", "start": 100}})


if __name__ == "__main__":
    unittest.main()
