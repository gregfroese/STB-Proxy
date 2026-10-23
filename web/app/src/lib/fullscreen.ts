// Full screen for the players (the live player and the On Demand player share it). It
// follows `fullscreenStrategy`: phones fullscreen the <video>; desktop and TV browsers
// grow the player to fill the window ("page", also fullscreening the page); a TV app's
// WebView only grows it ("window") and pushes a history entry so the remote's Back
// leaves full screen rather than the page. It also redraws Fire TV's video layer.

import { fullscreenStrategy } from "./playerLogic";
import { guardPopState, navigate } from "./router";

export interface FullscreenState {
  /** Full screen in any form (the browser's, or the player filling the window). */
  isFullscreen: boolean;
  /** The player fills the window (the "page" and "window" strategies): add `.full`. */
  fullWindow: boolean;
}

export interface FullscreenController {
  toggle(): void;
  /** In "window" full screen the current history entry is the full-screen one. */
  inWindowEntry(): boolean;
  /** The address Back restores in "window" full screen, after a zap or a hand-over. */
  setWindowUrl(url: string): void;
  /**
   * Drop full screen before leaving the page. Returns how many history entries the
   * player pushed (1 in "window" full screen), so Back can skip them.
   */
  release(): number;
  /** Redraw the video's hardware layer (Fire TV) after its box changed size. */
  refreshVideoLayer(): void;
  /** Remove the listeners and the Back guard. */
  destroy(): void;
}

export interface FullscreenOptions {
  video: () => HTMLVideoElement | undefined;
  onChange: (state: FullscreenState) => void;
  /** Whether to restart a paused video once full screen changes (some browsers pause it). */
  resumeAfterChange: () => boolean;
}

export function createFullscreen(options: FullscreenOptions): FullscreenController {
  let fullWindow = false;
  let isFullscreen = false;
  // "window" full screen pushes a history entry, so the remote's Back (which a TV
  // app's WebView turns into history.back()) leaves full screen, not the page.
  let fullWindowEntry = false;
  // The playing address while in "window" full screen, restored on Back.
  let fullWindowUrl = "";

  const emit = () => options.onChange({ isFullscreen, fullWindow });

  // TV browsers (Fire TV) draw the picture on a hardware layer that doesn't follow
  // CSS size changes: the stage grows but the picture keeps its old size and place.
  // Hiding the video for a couple of frames makes the browser rebuild that layer at
  // the video's current size. Playback carries on underneath.
  let refreshTimer = 0;
  function refreshVideoLayer() {
    window.clearTimeout(refreshTimer);
    refreshTimer = window.setTimeout(() => {
      const video = options.video();
      if (!video) return;
      video.style.visibility = "hidden";
      video.style.display = "none";
      void video.offsetHeight;
      requestAnimationFrame(() =>
        requestAnimationFrame(() => {
          video.style.display = "";
          video.style.visibility = "";
        }),
      );
    }, 50);
  }

  function setFullWindow(on: boolean) {
    fullWindow = on;
    isFullscreen = on || document.fullscreenElement != null;
    emit();
    refreshVideoLayer();
  }

  // Claims Back before the router follows it: after zaps the entry below is an older
  // address, and switching to it would restart the stream. Put the playing address
  // there instead.
  function onBack(): boolean {
    if (!fullWindowEntry) return false;
    fullWindowEntry = false;
    navigate(fullWindowUrl, true);
    setFullWindow(false);
    return true;
  }

  function toggle() {
    if (isFullscreen) {
      if (fullWindowEntry) {
        history.back();
        return;
      }
      setFullWindow(false);
      if (document.fullscreenElement) void document.exitFullscreen();
      return;
    }
    const coarse = window.matchMedia?.("(pointer: coarse)").matches ?? false;
    const strategy = fullscreenStrategy(navigator.userAgent, coarse);
    if (strategy === "video") {
      const request = options.video()?.requestFullscreen?.();
      if (request && typeof request.catch === "function") request.catch(() => undefined);
      return;
    }
    setFullWindow(true);
    if (strategy === "window") {
      fullWindowUrl = location.pathname + location.search;
      history.pushState(null, "", fullWindowUrl);
      fullWindowEntry = true;
      return;
    }
    const request = document.documentElement.requestFullscreen?.();
    if (request && typeof request.catch === "function") request.catch(() => undefined);
  }

  function onFullscreenChange() {
    // Leaving the browser's full screen (Back, Esc) also leaves the full-window player.
    if (document.fullscreenElement == null && fullWindow) setFullWindow(false);
    else refreshVideoLayer();
    isFullscreen = fullWindow || document.fullscreenElement != null;
    emit();
    const video = options.video();
    if (video && video.paused && options.resumeAfterChange()) {
      const play = video.play();
      if (play && typeof play.catch === "function") play.catch(() => undefined);
    }
  }

  document.addEventListener("fullscreenchange", onFullscreenChange);
  window.addEventListener("resize", refreshVideoLayer);
  const releaseBack = guardPopState(onBack);

  return {
    toggle,
    inWindowEntry: () => fullWindowEntry,
    setWindowUrl(url) {
      fullWindowUrl = url;
    },
    release() {
      const pushed = fullWindowEntry ? 1 : 0;
      fullWindowEntry = false;
      if (fullWindow) setFullWindow(false);
      if (document.fullscreenElement) void document.exitFullscreen().catch(() => undefined);
      return pushed;
    },
    refreshVideoLayer,
    destroy() {
      releaseBack();
      window.clearTimeout(refreshTimer);
      window.removeEventListener("resize", refreshVideoLayer);
      document.removeEventListener("fullscreenchange", onFullscreenChange);
    },
  };
}
