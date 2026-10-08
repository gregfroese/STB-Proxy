import json
import os
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "static", "multiview.js")


def row(channelId, number, name, available=True, dead=False, favourite=False):
    return {"portal": "p1", "channelId": channelId, "channelNumber": number, "customChannelNumber": "",
            "channelName": name, "customChannelName": "", "available": available, "dead": dead,
            "favourite": favourite}


@unittest.skipUnless(shutil.which("node"), "node not installed")
class MultiviewStateTest(unittest.TestCase):
    def run_js(self, body, saved=None, throws=False):
        """Run body under node with mv (the helpers) and storage (holding saved); print its result."""
        script = (
            "const mv = require(%s);"
            "const store = {};"
            "if (%s !== null) store[mv.KEY] = %s;"
            "const storage = %s ? {getItem() { throw new Error('no'); }, setItem() { throw new Error('no'); }}"
            "  : {getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }};"
            "const result = (() => { %s })();"
            "console.log(JSON.stringify(result));"
        ) % (json.dumps(SCRIPT), json.dumps(saved), json.dumps(saved), "true" if throws else "false", body)
        out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
        return json.loads(out)

    def test_garbage_or_unreadable_storage_gives_the_defaults(self):
        defaults = self.run_js("return mv.loadState(storage);")
        self.assertEqual(defaults["layout"], "4")
        self.assertEqual(defaults["order"], list(range(9)))
        self.assertEqual(defaults["tiles"], [None] * 9)
        self.assertEqual((defaults["audio"], defaults["big"]), (0, 66))
        for saved in ("{", "[]", '"x"', json.dumps({"layout": "7", "order": list(range(9)), "tiles": [None] * 9}),
                      json.dumps({"layout": "4", "order": [0, 0, 1, 2, 3, 4, 5, 6, 7], "tiles": [None] * 9}),
                      json.dumps({"layout": "4", "order": list(range(9)), "tiles": [None] * 3})):
            self.assertEqual(self.run_js("return mv.loadState(storage);", saved=saved), defaults, saved)
        self.assertEqual(self.run_js("return mv.loadState(storage);", throws=True), defaults)
        self.assertEqual(self.run_js("mv.saveState(storage, mv.loadState(storage)); return 1;", throws=True), 1)

    def test_a_saved_state_comes_back_cleaned(self):
        saved = json.dumps({"layout": "big", "order": [3, 0, 1, 2, 4, 5, 6, 7, 8],
                            "tiles": [{"portal": "p1", "channelId": 2}, {"portal": "p1"}] + [None] * 7,
                            "audio": 3, "big": 99})
        state = self.run_js("return mv.loadState(storage);", saved=saved)
        self.assertEqual(state["layout"], "big")
        self.assertEqual(state["order"][0], 3)
        self.assertEqual(state["tiles"][:2], [{"portal": "p1", "channelId": "2"}, None])
        self.assertEqual((state["audio"], state["big"]), (3, 66))

    def test_add_fills_the_first_empty_tile_shown_and_gives_it_sound(self):
        state = self.run_js(
            "mv.addChannel(storage, {portal: 'p1', channelId: '2'});"
            "mv.addChannel(storage, {portal: 'p1', channelId: '3'});"
            "return mv.loadState(storage);")
        self.assertEqual(state["tiles"][:3], [{"portal": "p1", "channelId": "2"}, {"portal": "p1", "channelId": "3"}, None])
        self.assertEqual(state["audio"], 1)

    def test_add_grows_the_layout_when_every_tile_shown_is_full(self):
        saved = json.dumps({"layout": "1", "order": list(range(9)),
                            "tiles": [{"portal": "p1", "channelId": "2"}] + [None] * 8, "audio": 0, "big": 66})
        state = self.run_js("return mv.addChannel(storage, {portal: 'p1', channelId: '3'});", saved=saved)
        self.assertEqual((state["layout"], state["tiles"][1]), ("2", {"portal": "p1", "channelId": "3"}))

    def test_add_replaces_the_tile_with_sound_when_all_nine_are_full(self):
        saved = json.dumps({"layout": "9", "order": list(range(9)),
                            "tiles": [{"portal": "p1", "channelId": str(i)} for i in range(9)], "audio": 4, "big": 66})
        state = self.run_js("return mv.addChannel(storage, {portal: 'p1', channelId: '99'});", saved=saved)
        self.assertEqual(state["tiles"][4], {"portal": "p1", "channelId": "99"})

    def test_choices_put_favourites_then_the_lineup_first_by_number(self):
        channels = [row("a", "30", "Zed"), row("b", "10", "Other", available=False),
                    row("c", "20", "Fav", favourite=True), row("d", "5", "Early")]
        names = self.run_js("return mv.channelChoices(%s, null, 50).map(mv.channelName);" % json.dumps(channels))
        self.assertEqual(names, ["Fav", "Early", "Zed", "Other"])
        some = self.run_js("return mv.channelChoices(%s, r => r.channelName != 'Zed', 2).map(mv.channelName);"
                           % json.dumps(channels))
        self.assertEqual(some, ["Fav", "Early"])

    def test_next_channel_moves_through_the_lineup_and_wraps(self):
        channels = [row("a", "1", "One"), row("b", "2", "Two", dead=True), row("c", "3", "Three"),
                    row("d", "4", "Four", available=False)]
        step = "return mv.nextChannel(%s, {portal: 'p1', channelId: '%s'}, %d).channelId;"
        self.assertEqual(self.run_js(step % (json.dumps(channels), "a", 1)), "c")  # skips dead
        self.assertEqual(self.run_js(step % (json.dumps(channels), "c", 1)), "a")  # wraps, skips not in lineup
        self.assertEqual(self.run_js(step % (json.dumps(channels), "a", -1)), "c")
        self.assertEqual(self.run_js(step % (json.dumps(channels), "d", 1)), "a")  # from outside the lineup

    def test_busy_and_stopped_tiles_are_not_retried_automatically(self):
        actions = self.run_js(
            "return [[null, false], [null, true], ['busy', false], ['client', false], ['recording', true]]"
            ".map(a => mv.failureAction(a[0], a[1]));")
        self.assertEqual(actions, ["retry", "failed", "busy", "client", "recording"])


if __name__ == "__main__":
    unittest.main()
