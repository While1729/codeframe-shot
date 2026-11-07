function sendAnonymousSummary(game, endpoint) {
  // Only aggregate values are sent; no player name or device information.
  if (!endpoint || game.summarySent) return;

  game.summarySent = true;
  const payload = JSON.stringify({
    result: game.cleared ? "clear" : "over",
    seconds: Math.floor(game.elapsedSeconds),
    version: game.version,
    endless: Boolean(game.endlessMode),
  });

  if (navigator.sendBeacon) {
    navigator.sendBeacon(endpoint, new Blob([payload], { type: "application/json" }));
  }
}

const longLabel = "A deliberately long comment or data string should remain visible in expand mode; for a fixed-width image, choose wrap mode so every character stays inside the frame, including comments, multilingual labels, and compact JSON summaries that extend beyond the default viewport.";
