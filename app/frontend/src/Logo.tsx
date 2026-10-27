// SPDX-License-Identifier: AGPL-3.0-or-later
/** Logo Ancrage : une ancre simple, suivie d'un mot-symbole lisible. */

export function Logo({
  px = 4,
  tagline = "Bridge the power of Anki and AI",
}: {
  px?: number;
  tagline?: string;
}) {
  const scale = px / 4;
  const width = 154 * scale;
  const height = 32 * scale;
  return (
    <span className="logo">
      <svg
        width={width}
        height={height}
        viewBox="0 0 154 32"
        fill="none"
        role="img"
        aria-label="ANCRAGE"
      >
        <circle cx="10" cy="7" r="4" stroke="currentColor" strokeWidth="2" />
        <path
          d="M10 11v13M4 17h12M4 17c0 6 2.7 9 6 9s6-3 6-9M6 28h8"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <text
          x="29"
          y="18"
          fill="currentColor"
          fontFamily="Segoe UI, system-ui, sans-serif"
          fontSize="15"
          fontWeight="700"
          letterSpacing="1.3"
        >
          ANCRAGE
        </text>
      </svg>
      {tagline && <span className="tagline">{tagline}</span>}
    </span>
  );
}
