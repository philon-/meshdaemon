# AGENTS.md

## Project overview

`meshdaemon` is an async Meshtastic daemon that polls external alert sources and rebroadcasts warnings over UDP multicast to a local Meshtastic mesh using deterministic packet IDs.

Primary entry point: `python -m app.main`

## Repository layout

- `app/main.py` - process orchestration, signal handling, supervision, and startup/shutdown flow
- `app/udp.py` - Meshtastic UDP setup and packet send helpers
- `app/config.py` - environment-driven configuration and defaults
- `app/util.py` - message normalization, chunking, and packet ID helpers
- `app/sources/common.py` - shared HTTP retry logic
- `app/sources/vma.py` - Sveriges Radio / VMA alert source
- `app/sources/smhi.py` - SMHI warning source

## Runtime flow

1. Configure the Meshtastic node identity and outbound UDP transport.
2. Send an initial node info packet.
3. Run source workers for VMA and SMHI plus a nodeinfo heartbeat under supervision.
4. On shutdown or failure, cancel tasks and exit cleanly.

## Configuration

Runtime behavior is controlled through environment variables defined in `app/config.py`. The README contains the user-facing defaults and setup instructions.

Important settings include:

- Meshtastic multicast group/port
- node ID, names, channel, and key
- hop limit and message size limits
- nodeinfo interval
- VMA and SMHI URLs, geocodes, and polling intervals
- warmup mode, retry settings, and restart throttling

## Code conventions

- Keep log tags in uppercase component form, such as `[ASYNC]`, `[UDP]`, `[VMA]`, and `[SMHI]`.
- Prefer action-first, present-tense log messages.
- Preserve deterministic message IDs and warmup suppression behavior.
- Keep retry and restart behavior explicit; do not hide failures.
- Maintain UTF-8-safe chunking behavior for outbound mesh messages.

## Change coordination

If code changes affect behavior, config, logging, or runtime flow, update this file in the same change so it stays aligned with the codebase.
