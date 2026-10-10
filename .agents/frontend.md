# Frontend rules (`frontend/`)

Next.js 16 (App Router, `src/`), React 19, TypeScript, Tailwind CSS v4, pnpm.

- This Next.js version differs from older training data: read the bundled docs in
  `frontend/node_modules/next/dist/docs/` before using an API you are unsure of (see `frontend/AGENTS.md`).
- **Design:** follow `frontend/DESIGN.md`. Use the tokens and utilities in `src/app/globals.css`
  (`bg-canvas`, `text-ink`, `text-mid-gray`, `border-hairline`, `card`, `btn-primary`, `btn-secondary`,
  `btn-outline`, `input`, `badge`, …) instead of raw hex values or ad-hoc radii. Red (`ember`) only for
  destructive/error states.
- **Backend access:** only through `src/lib/api.ts`, which calls relative `/api/*` paths (rewritten to the
  backend in `next.config.ts`). Never hard-code the backend host in components.
- Server components by default; add `"use client"` only for state, effects or event handlers. Components live
  in `src/components/` (kebab-case file names, PascalCase exports).
- `pnpm lint` and `pnpm exec tsc --noEmit` clean; add packages with `pnpm add`.
