# meshdaemon - Meshtastic Async Daemon

Multi-source async daemon that:
- polls REST endpoints on different intervals,
- listens to UDP multicast for Meshtastic (via `mudp`),
- Sends messages it has not heard before to the mesh

We use this in Stockholm to broadcast weather and PSA warnings. This script can be run by multiple nodes and any warnings that are heard before broadcast will be supressed. This way multiple users can run the script without drowning the mesh in warnings.

Uses [Sveriges Radio's API](https://vmaapi.sr.se/index.html?urls.primaryName=v3.0-beta) for Important Public Announcements / Viktigt meddelande till allmänheten (3.0) to extract alerts for a given region and broadcast to a local Meshtastic® network.


## Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configure
See `app/config.py` for env options

## Run
```bash
python -m app.main
```

---

Meshtastic® is a registered trademark of Meshtastic LLC. Meshtastic software components are released under various licenses, see GitHub for details. No warranty is provided - use at your own risk.