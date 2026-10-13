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

    def test_streams_script_is_valid_javascript(self):
        self.assertValidJavaScript("streams.html")

    def test_guide_script_is_valid_javascript(self):
        self.assertValidJavaScript("guide.html")

    def test_player_script_is_valid_javascript(self):
        self.assertValidJavaScript("_player.html")

    def test_multiview_script_is_valid_javascript(self):
        self.assertValidJavaScript("multiview.html")

    def test_multiview_tiles_are_per_tab_and_handle_a_stream_ending(self):
        script = inlineScripts("multiview.html")
        self.assertIn('multiview.tabId(multiview.browserStorage("sessionStorage"))', script)
        self.assertIn('"&tile=" + tileId(i)', script)
        self.assertIn('tile: tileId(i)', script)
        self.assertRegex(script, r't\.video\.addEventListener\("ended", function \(\) \{[\s\S]*?\} else if \(t\.video\.getAttribute\("src"\)\) \{\s*tileFailed\(i\);')

    def test_multiview_picker_has_search_favourites_and_blocks(self):
        with open(os.path.join(ROOT, "templates", "multiview.html")) as f:
            html = f.read()
        for tab in ("search", "favourites", "blocks"):
            self.assertIn('data-tab="{}"'.format(tab), html)
        script = inlineScripts("multiview.html")
        for helper in ("favouriteChoices", "blockChoices", "blockChannels"):
            self.assertIn("multiview." + helper + "(", script)

    def test_multiview_make_big_toggles_back(self):
        script = inlineScripts("multiview.html")
        self.assertIn("multiview.toggleBig(state, i)", script)
        self.assertIn("multiview.canGoBack(state, i)", script)
        self.assertIn("multiview.chooseLayout(state, layout)", script)

    def test_recordings_script_is_valid_javascript(self):
        self.assertValidJavaScript("recordings.html")

    def test_record_menu_script_is_valid_javascript(self):
        self.assertValidJavaScript("_record_modal.html")

    def test_tiles_and_player_can_record(self):
        mv = inlineScripts("multiview.html")
        self.assertIn("openRecordMenu(", mv)
        self.assertIn("stbRecordings.recordingsByChannel(", mv)
        player = inlineScripts("_player.html")
        self.assertIn("openRecordMenu(", player)
        for template in ("multiview.html", "_player.html"):
            with open(os.path.join(ROOT, "templates", template)) as f:
                self.assertIn('{% include "_record_modal.html" %}', f.read())

    def test_record_menu_cant_start_twice(self):
        script = inlineScripts("_record_modal.html")
        self.assertIn('box.querySelectorAll("button").forEach(function (b) { b.disabled = true; });', script)

    def test_recordings_page_shows_finishing_not_stop(self):
        self.assertIn("Finishing", inlineScripts("recordings.html"))

    def test_recordings_carry_on_once_the_server_is_listening(self):
        with open(os.path.join(ROOT, "app.py")) as f:
            self.assertRegex(f.read(), r"threading\.Timer\(\d+, getRecorder\(\)\.resume\)\.start\(\)")

    def test_lists_show_channels_being_recorded_with_from_start_and_live(self):
        player = inlineScripts("_player.html")
        for name in ("function recordingSlot(row)", "function watchFromStart(", "function watchLive(",
                     "function playRecordingFromStart(", "function backToLive("):
            self.assertIn(name, player)
        self.assertIn("/watch?from=start", player)
        self.assertIn("recordingSlot(row)", inlineScripts("editor.html"))
        self.assertIn("recordingSlot(row)", inlineScripts("blocks.html"))

    def test_the_end_of_a_recording_isnt_retried_like_a_failure(self):
        player = inlineScripts("_player.html")
        self.assertRegex(player, r'player\.addEventListener\("ended", function \(\) \{\s*if \(watchingRecording\) \{\s*recordingEnded\(\);')

    def test_multiview_tiles_watch_a_recording_from_the_start_or_live(self):
        mv = inlineScripts("multiview.html")
        for name in (".tile-from-start", ".tile-live", "function fromStart(i)", "function goLive(i)", "/watch?from=start"):
            self.assertIn(name, mv)

    def test_recording_now_tab_watches_from_the_start_or_live(self):
        page = inlineScripts("recordings.html")
        self.assertIn("watchFromStart(", page)
        self.assertIn("watchLive(", page)

    def test_block_favourites_in_the_player_and_blocks_page(self):
        player = inlineScripts("_player.html")
        for name in ("function blockFavouriteMark(row, block)", "function setBlockFavourite(", "playerBlock"):
            self.assertIn(name, player)
        with open(os.path.join(ROOT, "templates", "_player.html")) as f:
            self.assertIn('id="blockFavButton"', f.read())
        blocks = inlineScripts("blocks.html")
        self.assertIn("blockFavouriteMark(row, block)", blocks)
        self.assertIn("function toggleBlockFavouritesOnly(", blocks)
        self.assertIn("multiview.blockChannels(", blocks)  # favourites first

    def test_block_favourites_in_the_multiview_picker_and_channel_up_down(self):
        mv = inlineScripts("multiview.html")
        for name in ("/block/favourite", "pickerFavouritesOnly", "multiview.nextInList(", "favouritesOnly:"):
            self.assertIn(name, mv)

    def test_multiview_helpers_are_valid_javascript(self):
        result = subprocess.run(["node", "--check", os.path.join(ROOT, "static", "multiview.js")],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


class EditorToolbarTest(unittest.TestCase):
    """Ticket 07: the editor toolbar is one panel and its icon buttons are labelled."""

    def setUp(self):
        with open(os.path.join(ROOT, "templates", "editor.html")) as f:
            self.editor = f.read()
        with open(os.path.join(ROOT, "templates", "_player.html")) as f:
            self.player = f.read()

    def test_toolbar_owns_every_top_layout_row(self):
        # The default topStart/topEnd row would repeat search + pageLength below the
        # toolbar, so it is cleared; the bulk row is the hidden-until-selected row.
        for key in ("topStart: null", "topEnd: null", "top3Start", "top3End", "top2", "top:"):
            self.assertIn(key, self.editor, key)
        self.assertIn("bulk-row", self.editor)

    def test_save_and_reset_icon_buttons_are_labelled(self):
        self.assertIn("'aria-label': 'Save'", self.editor)
        self.assertIn("'aria-label': 'Reset'", self.editor)

    def test_row_icon_buttons_are_labelled(self):
        for label in ('aria-label="Play"', 'aria-label="Guide"', 'aria-label="Favourite"',
                      'aria-label="Watch live"', 'aria-label="Watch the recording from the start"'):
            self.assertIn(label, self.player, label)


class PreviewPromptTest(unittest.TestCase):
    def setUp(self):
        self.script = inlineScripts("_player.html")
        with open(os.path.join(ROOT, "templates", "_player.html")) as f:
            self.html = f.read()

    def test_failed_preview_offers_retry_not_just_dead(self):
        # A busy portal (503 from /play) looks the same to the browser as a dead stream.
        self.assertIn('id="retryPreview"', self.html)
        self.assertIn("function retryPreview", self.script)

    def test_previews_say_which_tile_they_play_in(self):
        # One per tab, so two tabs' players don't take each other's tuner back and forth.
        self.assertIn('"player." + multiview.tabId(', self.script)
        self.assertIn('"&tile=" + playerTile', self.script)

    def test_a_preview_that_ends_is_treated_as_stopped(self):
        # A preview stopped for Plex ends cleanly rather than with an error.
        self.assertRegex(self.script, r'player\.addEventListener\("ended", function \(\) \{[^}]*\} else if \(currentChannel && player\.getAttribute\("src"\)\) \{\s*previewFailed\(\);')

    def test_a_refused_or_stopped_preview_says_why(self):
        self.assertIn("/preview/status", self.script)
        self.assertIn('id="previewProblemText"', self.html)

    def test_send_to_multiview(self):
        self.assertIn('id="multiviewButton"', self.html)
        self.assertIn("function sendToMultiview", self.script)
        self.assertIn("multiview.js", self.html)
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
        # Whether to retry is multiview.failureAction (tested in test_multiview_state).
        self.assertRegex(self.script, r'if \(action == "retry"\) \{[^}]*retried = true;[^}]*startStream\(\d+\);\s*return;')

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


class MultiviewCompositionTest(unittest.TestCase):
    """Ticket 08: Multiview's page-local CSS is token-driven and dvh-aware."""

    def setUp(self):
        with open(os.path.join(ROOT, "templates", "multiview.html")) as f:
            self.html = f.read()
        self.style = self.html.split("<style>")[1].split("</style>")[0]

    def test_grid_height_uses_dvh_with_a_vh_fallback(self):
        self.assertIn("height: calc(100vh - 190px);", self.style)
        self.assertIn("height: calc(100dvh - 190px);", self.style)

    def test_only_the_literal_video_backgrounds_remain_as_hexes(self):
        # #000/#111 are the video and tile backgrounds; overlays are rgba gradients.
        self.assertEqual(sorted(set(re.findall(r"#[0-9a-fA-F]{3,8}\b", self.style))), ["#000", "#111"])

    def test_the_playing_ring_uses_a_token(self):
        self.assertIn(".tile.has-audio {", self.style)
        self.assertIn("border-color: var(--star);", self.style)

    def test_picker_and_record_modals_use_token_surfaces(self):
        self.assertNotIn("bg-dark", self.html)
        self.assertNotIn("text-light", self.html)
        with open(os.path.join(ROOT, "templates", "_record_modal.html")) as f:
            record = f.read()
        self.assertNotIn("bg-dark", record)
        self.assertNotIn("text-light", record)


class DashboardStreamsCompositionTest(unittest.TestCase):
    """Ticket 09: Dashboard and Streams compose from the shared card grid,
    token cards, the log panel and the badge component."""

    GRID = "row row-cols-1 row-cols-md-2 row-cols-xl-3 g-3"

    def setUp(self):
        with open(os.path.join(ROOT, "templates", "dashboard.html")) as f:
            self.dashboard = f.read()
        with open(os.path.join(ROOT, "templates", "streams.html")) as f:
            self.streams = f.read()

    def test_both_pages_use_the_shared_card_grid(self):
        self.assertIn(self.GRID, self.streams)
        # Dashboard uses it for both the account cards and the streaming cards.
        self.assertEqual(self.dashboard.count(self.GRID), 2)

    def test_cards_drop_the_deprecated_colour_variants(self):
        for name, html in (("dashboard.html", self.dashboard), ("streams.html", self.streams)):
            for variant in ("bg-dark", "bg-light", "text-dark", "border-secondary"):
                self.assertNotIn(variant, html, name)

    def test_streams_has_zero_page_local_css(self):
        self.assertNotIn("<style", self.streams)

    def test_cards_are_token_cards(self):
        # Both pages build cards as HTML strings with the canonical card.
        self.assertIn('<div class="card h-100">', self.streams)
        self.assertIn('<div class="card h-100">', self.dashboard)

    def test_badges_use_the_component_not_an_override(self):
        # Semantic colour via tint + border + dot; no hand-set text colour.
        self.assertIn("badge dot ", self.streams)
        self.assertIn("badge bg-info ms-1", self.dashboard)
        self.assertIn("badge dot bg-info ms-1", self.streams)

    def test_dashboard_log_is_the_token_log_panel(self):
        self.assertIn('class="log-panel"', self.dashboard)
        self.assertIn('id="autoscroll"', self.dashboard)

    def test_poll_cadences_are_unchanged(self):
        # Account 60s, log 2s, dashboard streaming 1s, Streams page 2s.
        self.assertIn("setInterval(loadAccount, 60000);", self.dashboard)
        self.assertIn("}(), 2000);", self.dashboard)
        self.assertIn("}(), 1000);", self.dashboard)
        self.assertIn("setInterval(update, 2000);", self.streams)

    def test_streams_stop_button_is_kept(self):
        self.assertIn("data-stop", self.streams)
        self.assertIn("/streams/stop", self.streams)

    def test_dashboard_account_check_is_kept(self):
        self.assertIn('id="checkAccount"', self.dashboard)
        self.assertIn("/account/check", self.dashboard)


class GuideRecordingsCompositionTest(unittest.TestCase):
    """Ticket 10: Guide and Recordings compose from the shared toolbar, token
    tables, token notice/error surfaces and the shared tab override."""

    def setUp(self):
        with open(os.path.join(ROOT, "templates", "guide.html")) as f:
            self.guide = f.read()
        with open(os.path.join(ROOT, "templates", "recordings.html")) as f:
            self.recordings = f.read()
        with open(os.path.join(ROOT, "static", "theme.css")) as f:
            self.theme = f.read()

    def test_guide_filter_bar_is_the_shared_toolbar(self):
        self.assertIn('<div class="toolbar', self.guide)
        # The same panel treatment the editor's generated rows use.
        self.assertIn(".toolbar,", self.theme)
        self.assertIn("#table_wrapper > .row:has(~ .row.dt-layout-table)", self.theme)

    def test_guide_results_are_the_token_table(self):
        self.assertIn('<table class="table table-striped align-middle">', self.guide)
        self.assertNotIn("table-dark", self.guide)

    def test_guide_status_is_the_shared_notice(self):
        self.assertIn('id="guideStatus" class="notice', self.guide)
        self.assertIn("status.className = 'notice mt-3 mb-2'", self.guide)
        self.assertIn("kind == 'error'", self.guide)

    def test_programme_desc_clamp_lives_in_theme(self):
        self.assertIn(".programme-desc {", self.theme)
        self.assertIn("-webkit-line-clamp: 2;", self.theme)

    def test_recordings_tabs_use_the_shared_override(self):
        self.assertIn('class="nav nav-tabs', self.recordings)
        self.assertNotIn(".nav-tabs", self.recordings)  # no page-local override

    def test_recordings_lists_are_token_tables(self):
        self.assertIn('<table class="table table-striped align-middle">', self.recordings)
        self.assertNotIn("table-dark", self.recordings)

    def test_recordings_messages_are_token_notices(self):
        self.assertNotIn('class="alert', self.recordings)
        self.assertIn('id="listError" class="notice error', self.recordings)
        self.assertIn('class="notice mb-3"', self.recordings)

    def test_recordings_playback_is_a_token_modal(self):
        self.assertIn("modal-xl", self.recordings)
        self.assertNotIn("bg-dark", self.recordings)
        self.assertNotIn("text-light", self.recordings)

    def test_recordings_icon_buttons_are_labelled(self):
        for label in ('aria-label="Watch from the start"', 'aria-label="Watch live"',
                      'aria-label="Play"', 'aria-label="Download"', 'aria-label="Delete"'):
            self.assertIn(label, self.recordings, label)

    def test_guide_and_recordings_behaviour_is_unchanged(self):
        self.assertIn("/guide/search", self.guide)
        self.assertIn("scheduleSearch", self.guide)
        self.assertIn("setInterval(load, 10000);", self.recordings)
        for name in ("stopRecording", "deleteRecording", "playRecording", "openPlayer"):
            self.assertIn(name, self.recordings)


if __name__ == "__main__":
    unittest.main()
