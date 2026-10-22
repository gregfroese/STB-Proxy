// Fire TV (AFTxx models, Silk), Android TV / Google TV and the common smart-TV browsers.
const TV_BROWSER =
  /\bAFT[A-Z0-9]*\b|Silk|Android TV|GoogleTV|BRAVIA|SMART-TV|SmartTV|Tizen|Web0S|CrKey/i;

/** True for a browser running on a TV (driven by a remote, not touch or a mouse). */
export function isTvBrowser(userAgent: string): boolean {
  return TV_BROWSER.test(userAgent);
}
