# UI component sources

## shadcn/ui Button and Badge

The landing page's reusable buttons and badges adapt the actual variant styles
from the official [shadcn/ui repository](https://github.com/shadcn-ui/ui).

- Pinned commit: [`98a1fe67b439324ddc857f47fbdce056600a4329`](https://github.com/shadcn-ui/ui/tree/98a1fe67b439324ddc857f47fbdce056600a4329).
- Original Button: [`apps/v4/registry/new-york-v4/ui/button.tsx`](https://github.com/shadcn-ui/ui/blob/98a1fe67b439324ddc857f47fbdce056600a4329/apps/v4/registry/new-york-v4/ui/button.tsx).
- Original Badge: [`apps/v4/registry/new-york-v4/ui/badge.tsx`](https://github.com/shadcn-ui/ui/blob/98a1fe67b439324ddc857f47fbdce056600a4329/apps/v4/registry/new-york-v4/ui/badge.tsx).
- License: MIT; complete upstream license in
  `fireatlas/static/vendor/SHADCN_UI_LICENSE.txt`.
- Local implementation: `fireatlas/static/vendor/ui-primitives.css`.

The upstream utility declarations for inline flex layout, spacing, typography,
rounded corners, icon sizing, primary/outline colors, hover, keyboard focus,
disabled buttons and outlined badges were translated into ordinary CSS. React,
Radix Slot, CVA and Tailwind are not included. FireAtlas adds themed CSS variables,
44px minimum button height and reduced-motion handling; unused variants were
omitted. These are adapted styling primitives, not a vendored React package.

Classes: `ui-button` with `ui-button-primary` or `ui-button-outline`, and
`ui-badge`. Theme variables use the `--ui-` prefix, including `--ui-primary`,
`--ui-primary-foreground`, `--ui-primary-hover`, `--ui-background`,
`--ui-foreground`, `--ui-border`, `--ui-accent`, `--ui-accent-foreground`,
`--ui-ring`, `--ui-ring-shadow` and `--ui-radius`.

## Lucide icons

FireAtlas uses a small, locally served SVG symbol sprite from the official
[Lucide repository](https://github.com/lucide-icons/lucide). The selected icons
provide consistent navigation and data controls without a JavaScript dependency
or a runtime request to an external icon service.

- Version: **0.468.0**.
- Pinned commit: [`f12b0de177fbc2a6795e99be065887e72b237123`](https://github.com/lucide-icons/lucide/tree/f12b0de177fbc2a6795e99be065887e72b237123).
- Original files: [`icons/*.svg`](https://github.com/lucide-icons/lucide/tree/f12b0de177fbc2a6795e99be065887e72b237123/icons).
- License: ISC; upstream's complete license and copyright notice are preserved
  in `fireatlas/static/vendor/LUCIDE_LICENSE.txt`.
- Local sprite: `fireatlas/static/vendor/lucide-icons.svg`.
- Changes: SVG roots converted to named `symbol` elements and combined into one
  file. Paths, shapes, view boxes and drawing attributes remain from upstream.

Available symbol IDs:

`earth`, `satellite`, `layers`, `map`, `chart-no-axes-combined`, `scan-eye`,
`arrow-up-right`, `arrow-right`, `chevron-down`, `info`, `check`, `compass`,
`book-open`, `play`, `menu`, `x`, `search`, `download`.

Example:

```html
<svg class="ui-icon" width="20" height="20" aria-hidden="true" focusable="false">
  <use href="/vendor/lucide-icons.svg#earth"></use>
</svg>
```

Pair decorative icons with visible text. Give icon-only controls an accessible
name on the control itself. The sprite uses `currentColor`, so the surrounding
control determines icon color.

## Landing-page integration and verification — 28 September 2026

`landing.css` scopes the observatory theme to the landing page. `landing.js`
adds section tracking, the resource menu and concise tooltip explanations.
The global tooltip is outside the clipped globe hero so help remains visible
throughout the workspace. It supports hover, focus and tap, with Escape to close.

Navigation follows Earth → world map → regional study → source evidence.
Global FIRMS observations and the study archive are explicitly separate. The
regional calendar retains unloaded, zero-detection and detected-day styles;
historic source options appear only when their required products are imported.
Measured fire weather is visibly unavailable; synthetic mode keeps its labelled
illustration. Source records preserve zero FRP values and show MW units.

Verification completed:

- All 56 automated tests passed.
- Globe default-hidden detections, layer toggles, documented-case back navigation,
  worldwide map filtering and 2D-to-3D evidence selection passed in Chrome.
- Tooltips passed hover, keyboard focus, tap and Escape checks.
- Mobile menu open/close and layouts at 360, 390, 820, 1024, 1366 and 1440 px
  were checked; no horizontal overflow or JavaScript exceptions were observed.
- Imported and synthetic study modes, calendar-to-evidence navigation, saved
  month/day restoration, both CSV exports and guided-tour progression passed.
- Visual inspection included desktop/mobile Earth, the global map, source
  selection, calendar, evidence and the study tools.

Existing NDVI defaults in the shared workspace were retained. All original data
controls and the exact-pose detection reveal behavior remain in place.
