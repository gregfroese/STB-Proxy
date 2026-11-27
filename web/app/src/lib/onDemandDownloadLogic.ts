// On Demand downloads on the title page: STB-Proxy saves a Movie or Episode into its
// downloads folder (for Plex and Jellyfin), queued until nobody watches from the portal.
// Nothing is stored in the browser. The Companion app uses the same wording.

import { ApiError } from "./api";
import type { OnDemandDownload, OnDemandDownloadBrief, OnDemandKey } from "./types";

/** How often the title page looks again while a download it shows is queued or running. */
export const DOWNLOAD_POLL_MS = 15_000;

export interface DownloadButton {
  label: string;
  /** Pressing it asks for the download (nothing asked yet, or it failed). */
  canStart: boolean;
  /** A tooltip with the why: the failure, or what a pause means. */
  hint: string | null;
}

export function downloadButton(brief: OnDemandDownloadBrief | null | undefined): DownloadButton {
  if (!brief)
    return { label: "Download", canStart: true, hint: "Save it in STB-Proxy's downloads folder" };
  switch (brief.status) {
    case "done":
      return { label: "Downloaded", canStart: false, hint: null };
    case "downloading":
      return { label: `Downloading ${brief.progress}%`, canStart: false, hint: null };
    case "failed":
      return { label: "Download failed – try again", canStart: true, hint: brief.error };
    default:
      return brief.progress > 0
        ? {
            label: `Paused at ${brief.progress}%`,
            canStart: false,
            hint: "It goes on once nobody is watching from this portal",
          }
        : {
            label: "Queued",
            canStart: false,
            hint: "It starts once nobody is watching from this portal",
          };
  }
}

/** An Episode row's download status, or null when there's nothing to say. */
export function episodeDownloadText(
  brief: OnDemandDownloadBrief | null | undefined,
): string | null {
  if (!brief) return null;
  if (brief.status === "failed") return "Download failed";
  return downloadButton(brief).label;
}

/** Whether the viewer may cancel it: their own, not finished. */
export function canCancel(brief: OnDemandDownloadBrief | null | undefined): boolean {
  return !!brief && brief.mine === true && brief.status !== "done";
}

/** Whether the page should keep looking for news of it. */
export function isActive(brief: OnDemandDownloadBrief | null | undefined): boolean {
  return !!brief && (brief.status === "queued" || brief.status === "downloading");
}

/** A stable key for a Movie or an Episode, to match downloads to what the page shows. */
export function itemKey(key: OnDemandKey): string {
  return "id" in key
    ? `${key.portal}\u0000${key.id}`
    : `${key.portal}\u0000${key.seriesId}\u0000${key.seasonId}\u0000${key.episodeId}`;
}

/** The downloads by item key, as briefs. */
export function briefsByItem(downloads: OnDemandDownload[]): Map<string, OnDemandDownloadBrief> {
  const map = new Map<string, OnDemandDownloadBrief>();
  for (const d of downloads) {
    map.set(itemKey(d.item), {
      id: d.id,
      status: d.status,
      progress: d.progress,
      error: d.error,
      mine: d.mine,
    });
  }
  return map;
}

export function downloadErrorText(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "Couldn't ask for the download. Try again.";
}
