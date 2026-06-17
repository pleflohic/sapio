// SPDX-License-Identifier: AGPL-3.0-or-later
/** Logo « SAPIO » en pixel art (grille 5×7 par lettre), rendu en blocs SVG.
 *  Net à toute taille, monochrome (couleur héritée via currentColor). */
const FONT: Record<string, string[]> = {
  S: ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
  A: ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
  P: ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
  I: ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
  O: ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
};
const WORD = "SAPIO";
const COLS = 5;
const ROWS = 7;
const GAP = 1; // colonne vide entre les lettres

export function Logo({
  px = 4,
  tagline = "Bridge the power of Anki and AI",
}: {
  px?: number;
  tagline?: string;
}) {
  const rects: JSX.Element[] = [];
  let xOff = 0;
  for (const ch of WORD) {
    const glyph = FONT[ch];
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        if (glyph[r][c] === "1") {
          rects.push(
            <rect key={`${xOff}-${r}-${c}`} x={(xOff + c) * px} y={r * px} width={px} height={px} />
          );
        }
      }
    }
    xOff += COLS + GAP;
  }
  const w = (xOff - GAP) * px;
  const h = ROWS * px;
  return (
    <span className="logo">
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} fill="currentColor" role="img" aria-label="SAPIO" shapeRendering="crispEdges">
        {rects}
      </svg>
      {tagline && <span className="tagline">{tagline}</span>}
    </span>
  );
}
