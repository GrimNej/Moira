# 0010. Stable sky: incremental placement, positions never move; no UMAP or force layout

Date: 2026-10-28
Status: Accepted

## Context

People learn a spatial layout like a city map (Data Mountain, mental-map preservation). Global layouts such as UMAP or force-directed graphs move everything when the data changes.

## Decision

Place hubs and stars incrementally and never move them. Shelves sit on a fixed ring (radius 1,100); new hubs are placed near their most similar hub; stars are placed near similar stars in their primary hub with seeded jitter and collision avoidance (no two within 9 units). Only an explicit admin command that bumps `layout_version` may move stars.

## Consequences

- Easier: The sky is learnable and stable across sessions.
- Harder: Placement quality depends on arrival order; regions can become uneven over time.

Blueprint: §7.7.
