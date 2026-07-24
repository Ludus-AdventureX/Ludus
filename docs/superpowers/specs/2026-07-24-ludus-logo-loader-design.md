# Ludus Logo Loader Design

## Goal

Create a loading animation based on `apps/web/public/logo.svg`. The letters in
LUDUS draw themselves one at a time from left to right. They must enter through
visible line drawing, not through horizontal movement or a left-to-right fade.

The same animation must support three uses:

1. A standalone animated SVG asset.
2. A reusable in-page React loading component.
3. A full-screen initial loading overlay.

## Visual Behavior

The animation uses five hand-tuned centerline guide groups, one for each letter.
Each group draws with `stroke-dasharray` and `stroke-dashoffset`. The next letter
starts shortly before the previous letter finishes so the word feels written as
one continuous sequence without making two letters appear simultaneously.

The animation phases are:

1. **Draw:** L, U, D, U, and S draw in order from left to right.
2. **Resolve:** after S completes, the guide strokes fade into the supplied
   finished Logo artwork at the exact same position and size.
3. **Hold:** the finished Logo remains fully opaque briefly.
4. **Breathe:** while loading remains active, the finished Logo fades from
   opacity `1` to approximately `0.35`, then returns to `1`.
5. **Repeat:** the animation resets and begins drawing L again.

Stopping loading must not abruptly hide or reset the Logo. When `loading`
changes to `false`, the component completes the current resolve transition,
shows the finished Logo, and then exits through a short opacity transition.

The final fill layer must use the supplied Logo artwork so the completed state
preserves the original appearance. The custom centerlines are animation guides,
not a replacement or redesign of the brand artwork.

## Components And Assets

### Standalone SVG

Add `apps/web/public/ludus-logo-loader.svg`. It contains the five centerline
groups, final Logo layer, CSS keyframes, and reduced-motion styling. It has a
transparent background and scales through its `viewBox` without distortion.

### Reusable Component

Add a focused `LudusLogoLoader` component under the web app's component tree.
Its public interface supports:

- `loading?: boolean`, defaulting to `true`.
- `size?: "sm" | "md" | "lg"`, with stable dimensions for each size.
- `className?: string` for layout integration.
- `label?: string` for an accessible loading name.

The component owns animation state only. It does not fetch data or decide what
the application is loading.

### Full-Screen Overlay

Add a thin full-screen wrapper around `LudusLogoLoader`. The overlay centers the
large loader on the application's existing page background, blocks pointer
interaction while visible, and exits only after the loader reports its finished
state. It is suitable for the initial application-loading boundary and remains
independent of page-specific data fetching.

The existing header Logo remains static. The loading treatment does not replace
ordinary branding shown after the page is ready.

## Timing

The initial target duration is approximately 4.8 seconds per continuing cycle:

- Sequential drawing and resolve: about 2.4 seconds.
- Full-opacity hold: about 0.6 seconds.
- Fade down and return: about 1.2 seconds.
- Reset buffer: about 0.6 seconds.

Exact per-letter offsets may be adjusted during visual inspection to compensate
for different path lengths. The observable requirement is ordered, legible
writing with no letter starting visibly before the previous letter.

## Accessibility

The reusable loader exposes `role="status"` and an accessible label without
displaying instructional text. Decorative paths are hidden from assistive
technology.

Under `prefers-reduced-motion: reduce`, all drawing and breathing animations are
disabled and the complete Logo is shown immediately. The overlay may still use
a brief non-animated visibility change when loading finishes.

## Responsive Behavior

The SVG keeps a fixed aspect ratio. Component size variants use stable width and
height constraints so animation phases cannot shift layout. The full-screen
variant is constrained by both viewport width and a desktop maximum. It must fit
without clipping at desktop and narrow mobile widths.

## Verification

Automated checks cover:

- The five letter groups and their L-to-R animation delays.
- Loading and finished component states.
- Accessible status labeling.
- Reduced-motion behavior.
- Type checking, linting, unit tests, and the production build.

Visual verification uses browser screenshots at desktop and mobile dimensions.
Checks sample the draw, resolve, full-fill, dimmed, and restored phases. The
review confirms that the canvas is nonblank, the word is centered and unclipped,
the letters appear in order, the transition to supplied artwork does not jump,
and no loader UI overlaps surrounding content.

## Out Of Scope

- Redesigning or simplifying the supplied Logo.
- Adding progress percentages or loading messages.
- Coupling the loader to a particular API request.
- Replacing the persistent header Logo with an endlessly animated Logo.
