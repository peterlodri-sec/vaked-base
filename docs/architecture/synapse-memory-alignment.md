# SYNAPSE — Unified Memory Architecture
**GENESIS_SEAL: 7c242080**

6 memory systems → 1 brain. O(1) access. Zero fragmentation.

| Backend | Access |
|---------|--------|
| Memory Plane (eventd) | O(1) by key |
| Memory Plane (mmap) | O(1) pointer |
| Milvus | O(log n) ANN |
| Cube | O(1) pre-aggregated |

Alignment: write → Memory Plane first. Auto-embed → Milvus. Cube materialized from Memory Plane.

GENESIS_SEAL: 7c242080
