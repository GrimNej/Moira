# 0002. One Python process (API + bot + worker) on the 1 GB Oracle micro VM

Date: 2026-10-28
Status: Accepted

## Context

The server is an Oracle Always Free VM.Standard.E2.1.Micro: 1/8 OCPU and 1 GB RAM. Two processes would each load Python, FastAPI and the embedding model, roughly doubling RAM use.

## Decision

Run a single uvicorn process with one worker. It serves the FastAPI API, runs the aiogram bot with long polling as a lifespan task, and runs the asyncio job worker. All three call the same service layer. Target peak is about 550 MB with 2 GB swap; systemd `MemoryMax=650M`.

## Consequences

- Easier: Hosting costs $0; one model load; simple deploys.
- Easier: One place for logs and health.
- Harder: A crash takes down API, bot and worker together (systemd restarts it).
- Harder: CPU-heavy work must stay off the event loop; one media job at a time.

Blueprint: §5.2, §5.3.
