# Investment News Copy Parity Notes

## Baseline parity

- Restored the original 12 sectors, sector accents, 106 source definitions, and current data.js display data.
- Restored the original full-screen dark layout: 264px sidebar, independently scrolling main column, sticky sector header, AI digest panel, and compact news rows.
- Preserved the original display contract: title, zh, summary, url, source, time, ts, plus digest t and url.
- Kept the default first-sector selection, sector counts, source statistics, local-run notice, empty states, and original-link behavior.
- Removed the original GitHub button as requested.

## Copy-only engineering capabilities

- Kept the copy's refresh orchestration, request idempotency, loopback/token authorization, structured logs, timeout handling, rollback backup, and atomic data.js writes.
- Raised the validated source limit to 150 so the original 106-source configuration remains accepted with maintenance headroom.
- Kept the copy's RSS parsing, normalization, redline filtering, LLM response validation, and test suite.

## Limited experience optimization

- Added keyboard focus and Enter/Space activation to sector navigation.
- Added explicit http/https URL validation before rendering external links.
- Kept refresh loading disabled and spinning, restored compatibility state markers, and retained explicit failure feedback.
- Added reduced-motion handling and a mobile layout that avoids page-level horizontal overflow while allowing the sector strip to scroll independently.

## Verification

- python -m unittest discover -s tests -v: 65 tests passed.
- Original and copy data/source file hashes match.
- Desktop screenshots: output/playwright/original-desktop.png and output/playwright/copy-desktop.png.
- Mobile screenshot: output/playwright/copy-mobile.png; at a 390px viewport, document scroll width matched the client width.
- Sector switching from AI to 航天 / 太空 updated both active navigation and main heading.
- Mocked refresh failure returned a visible failure dialog and restored the refresh button.
