# meshdaemon - Meshtastic Async Daemon

Multi-source async daemon that:
- Polls REST endpoints on different intervals,
- Listens to UDP multicast for Meshtastic (via `mudp`),
- Sends messages it has not heard before to the mesh

We use this in Stockholm to broadcast weather and PSA warnings. This script can be run by multiple nodes and any warnings heard before broadcast will be suppressed. This way multiple users can run the script without drowning the mesh in warnings.

Uses [Sveriges Radio's API](https://vmaapi.sr.se/index.html?urls.primaryName=v3.0-beta) for Important Public Announcements / Viktigt meddelande till allmänheten (3.0) to extract alerts for a given region and broadcast to a local Meshtastic® network.


## Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configure
Environment variables (with defaults):

| Variable | Default | Purpose |
|---|---:|---|
| `MESHTASTIC_MCAST_GRP` | `224.0.0.69` | UDP multicast group for mesh packets |
| `MESHTASTIC_MCAST_PORT` | `4403` | UDP multicast port |
| `MESHTASTIC_NODE_ID` | `!112` | Node identifier advertised by daemon |
| `MESHTASTIC_LONG_NAME` | `VMA ROBOT` | Long display name |
| `MESHTASTIC_SHORT_NAME` | `VMA` | Short display name |
| `MESHTASTIC_CHANNEL` | `MediumFast` | Channel name for outgoing packets |
| `MESHTASTIC_KEY` | `AQ==` | Channel key |
| `MESHTASTIC_HOP_LIMIT` | `5` | Hop limit for text + nodeinfo packets |
| `MESHTASTIC_MAX_BYTES` | `200` | Max UTF-8 bytes per text chunk |
| `MESHTASTIC_MAX_MESSAGES` | `2` | Max chunks per outbound alert |
| `NODEINFO_INTERVAL_SECS` | `43200` | Nodeinfo broadcast interval (12h) |
| `SEEN_TTL_SECS` | `86400` | Dedupe memory TTL for seen messages |
| `VMA_URL` | Sveriges Radio URL | VMA API endpoint |
| `VMA_INTERVAL` | `60` | VMA polling interval in seconds |
| `VMA_GEOCODE` | `01` | VMA geocode filter |
| `SMHI_URL` | SMHI URL | SMHI warning endpoint |
| `SMHI_INTERVAL` | `60` | SMHI polling interval in seconds |
| `SMHI_GEOCODE` | `1` | SMHI area id filter |
| `WARMUP` | `1` | `1` = mark first fetch as seen only, do not transmit |
| `MAX_RETRIES` | `3` | HTTP retries per fetch cycle |
| `BASE_BACKOFF` | `2` | Exponential backoff base seconds |
| `MAX_RESTART_INTERVAL` | `60` | Worker restart throttle window |
| `RESTART_HISTORY` | `5` | Worker failures in window before stop |

## Runtime behavior
- **Warmup**: on source startup, first fetched messages are inserted into dedupe state with `seen_only=True`; this suppresses startup floods.
- **Dedupe strategy**: All instances use the same deterministic CRC32 hash of normalized message text to generate packet IDs when broadcasting. When receiving packets from the mesh, we store the packet ID in the dedupe cache. Since all instances send with content-based IDs, receiving an identical message (from any source node) will have the same packet ID, triggering dedupe and preventing relay floods.
- **Failure policy**: each worker restarts after crashes; if crashes reach `RESTART_HISTORY` within `MAX_RESTART_INTERVAL`, the task fails and the daemon shuts down.

## Logging style
- Use component tags in uppercase (for example `[ASYNC]`, `[UDP]`, `[VMA]`, `[SMHI]`).
- Prefer action-first, present-tense phrasing (for example `Task completed: ...`, `Source started (...)`).
- Keep retry logs consistent as `Request failed ...; retrying in ...`.
- Use `... started` / `... stopped` wording for lifecycle logs.
- Keep per-message logs explicit (`Message ready: ...`) and aggregate counters concise (`Messages fetched: N`).

## Run
```bash
python -m app.main
```

---

Meshtastic® is a registered trademark of Meshtastic LLC. Meshtastic software components are released under various licenses, see GitHub for details. No warranty is provided - use at your own risk.