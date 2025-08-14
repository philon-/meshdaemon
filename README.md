# meshdaemon - Meshtastic Async Daemon

Multi-source async daemon that:
- polls REST endpoints on different intervals,
- listens to UDP multicast for Meshtastic (via `mudp`),
- Sends messages it has not heard before to the mesh

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
