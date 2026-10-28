# 0018. Preact + Vite + Canvas 2D now; WebGL behind the same interface later

Date: 2026-10-28
Status: Accepted

## Context

The web app must be small and fast on mid-range phones and must draw thousands of glowing stars smoothly.

## Decision

Build the web app in TypeScript (strict) with Preact, `@preact/signals` and Vite, with no UI kit, CSS framework or animation library. The sky is a framework-free Canvas 2D module; a WebGL renderer can replace it later behind the same interface.

## Consequences

- Easier: A tiny bundle (JS ≤ 120 KB gzipped); full control of glow and motion.
- Harder: The sky, springs and timeline are hand-written.

Blueprint: §5.4.
