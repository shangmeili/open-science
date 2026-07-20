# AI4HEOR first-use combined audit

Date: 2026-07-17

Surface: AI4HEOR 0.1.31 source at a 1280×720 desktop viewport

User goal: enter a Human-led HEOR workspace and prepare a natural-language research request without being forced through a scientific form.

Accessibility target: keyboard-visible operation and WCAG AA normal-text contrast for the audited light-theme surfaces.

## Step 1 — First-use boundary: healthy after fixes

![Focused skip link and Human-led first-use guide](./06-skip-link-stable.png)

- The guide states the four control boundaries before research begins: local storage,
  researcher-selected model, reviewable actions, and Human scientific authority.
- The HEOR conversation and composer remain visible; the guide is not a form and does not
  start a model turn.
- A focus-only, localized skip link bypasses the sidebar. Activation was verified to move
  focus to `#ai4heor-main`.
- The focused link has a visible two-pixel outline. The same global `:focus-visible`
  contract applies to every interactive control.

## Step 2 — HEOR natural-language entry: healthy

![HEOR natural-language starter surface](./07-heor-workspace-final.png)

- Continuing removes only the first-use guide and reveals five HEOR-specific natural-language
  starters; the product does not fall back to generic Open Science examples.
- The research question and Human decision authority remain higher in the hierarchy than the
  starter cards.
- Supporting text on the paper background measures 4.57:1 in the current light theme.

## Step 3 — Cost-effectiveness draft: healthy

![Editable cost-effectiveness natural-language draft](./08-natural-language-draft-final.png)

- Selecting the starter writes an editable request into the composer and focuses it.
- The request asks the assistant to begin with the decision problem and restrict questions to
  information that would materially change the analysis.
- No model turn is sent and the offline send control remains disabled.

## Fixed findings

1. Light-theme muted text was 3.28–3.57:1 and the small primary-button label was 4.23:1.
   Tokens now produce 4.57–4.99:1 supporting text and a 5.17:1 primary-button label on the
   audited surfaces.
2. The shell had no explicit navigation bypass. It now exposes a seven-language skip link and
   a focusable main region.
3. Components used inconsistent or subtle focus treatments. A product-level focus indicator
   now provides a common minimum without changing component layouts.

## Evidence limits

- The browser backend could verify focus state, computed styles, target focus and pointer-driven
  flow, but did not provide a reliable end-to-end raw Tab traversal from an unfocused document.
- This audit does not establish screen-reader naming/announcement quality, switch control,
  200–400% zoom/reflow, reduced-motion behavior, physical desktop behavior, or full WCAG
  conformance. Those remain explicit release checks.
