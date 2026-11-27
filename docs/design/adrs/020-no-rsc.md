# 020 - No React Server Components for the local SPA

**Status:** accepted (expected reject, recorded)  
**Date:** 2026-11-25

## Context

React 19 ships Server Components and Server Actions. The 2026 plan (M10.5) asks for an explicit
decision instead of an accidental one, because "modern" is not a requirement.

Works is a local-first product: one daemon owns one home, and the browser is a client of that daemon's
HTTP API. There is no server-side rendering tier, no SEO surface, no CDN, and no multi-tenant server
that could host a React Server runtime.

## Decision

Do **not** adopt React Server Components, Next.js, Remix or Server Actions.

- Rendering stays a client-side Vite SPA talking to `/api/v1` (typed by the generated OpenAPI client).
- Data loading stays TanStack Query / plain `fetch` against the daemon; mutations are HTTP calls with
  idempotency keys.
- Streaming is SSE from the daemon, which works the same for the SPA, a native Windows client and a
  phone — RSC streaming would only serve one of them.
- The bundle is committed and served by the daemon from disk; an RSC build would require a Node runtime
  next to the Python daemon, doubling the install and the failure surface.

## Consequences

- The UI cannot use `"use server"`, server actions or async server components; it does not need them.
- If Works ever grows a hosted, multi-user mode, this ADR is the place to reopen the question — with a
  new product requirement, not a framework preference.
- React Compiler (M10.4) remains a separate, measurable build experiment; it does not depend on this
  decision.
