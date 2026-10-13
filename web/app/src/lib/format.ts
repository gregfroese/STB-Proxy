import type { Programme } from "./types";

const TIME = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" });

export function formatTime(date: Date | null): string {
  return date ? TIME.format(date) : "";
}

/** `HH:mm–HH:mm` (or just the start when stop is missing). */
export function timeRange(programme: Programme): string {
  const start = formatTime(programme.start);
  const stop = programme.stop ? formatTime(programme.stop) : "";
  return stop ? `${start}–${stop}` : start;
}
