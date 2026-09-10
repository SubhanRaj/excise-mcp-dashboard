# Brand assets

Government of Uttar Pradesh identity kit for the dashboard, copied from
`~/Sites/upexcise-stats-dashboard`.

- `up-gov-emblem.svg` — State Emblem of Uttar Pradesh (Wikimedia Commons,
  public-domain government insignia). The masthead emblem.
- `up-gov-emblem-white.png` — 1024x1024 white rasterisation on a transparent
  ground, used to composite the icons.
- `favicon.ico`, `favicon-16.png`, `favicon-32.png`, `apple-touch-icon.png`,
  `icon-192.png`, `icon-512.png` — the white emblem on a govviolet ground.

Milestone 5 copies these into `web/public/`. The Department of Excise identity
mark drops in beside the emblem as
`web/public/assets/img/excise-logo.{svg,png,webp}` when one exists. The
sibling's `scripts/make-brand-assets.php` regenerates the icons and the Open
Graph card from `up-gov-emblem.svg`.
