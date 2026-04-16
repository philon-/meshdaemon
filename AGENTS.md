# AGENTS.md

## Project overview

`meshdaemon` is an async Meshtastic daemon that polls external alert sources, deduplicates messages, and rebroadcasts new warnings over UDP multicast to a local mesh network.

Primary entry point: `python -m app.main`

## Repository layout

- `app/main.py` - process orchestration, signal handling, supervision, and startup/shutdown flow
- `app/router.py` - message normalization, dedupe tracking, and outbound routing
- `app/udp.py` - Meshtastic UDP setup, listener lifecycle, and packet send helpers
- `app/config.py` - environment-driven configuration and defaults
- `app/util.py` - message chunking and packet ID helpers
- `app/sources/common.py` - shared HTTP retry logic
- `app/sources/vma.py` - Sveriges Radio / VMA alert source
- `app/sources/smhi.py` - SMHI warning source

## Runtime flow

1. Configure the Meshtastic node identity and UDP transport.
2. Start the multicast listener and subscribe to inbound text packets.
3. Send an initial node info packet.
4. Run source workers for VMA and SMHI plus a nodeinfo heartbeat under supervision.
5. On shutdown or failure, cancel tasks, stop UDP, and exit cleanly.

## Configuration

Runtime behavior is controlled through environment variables defined in `app/config.py`. The README contains the user-facing defaults and setup instructions.

Important settings include:

- Meshtastic multicast group/port
- node ID, names, channel, and key
- hop limit and message size limits
- nodeinfo interval and dedupe TTL
- VMA and SMHI URLs, geocodes, and polling intervals
- warmup mode, retry settings, and restart throttling

## Code conventions

- Keep log tags in uppercase component form, such as `[ASYNC]`, `[UDP]`, `[VMA]`, `[SMHI]`, and `[ROUTER]`.
- Prefer action-first, present-tense log messages.
- Preserve deterministic message IDs and dedupe behavior.
- Keep retry and restart behavior explicit; do not hide failures.
- Maintain UTF-8-safe chunking behavior for outbound mesh messages.

## Change coordination

If code changes affect behavior, config, logging, or runtime flow, update this file in the same change so it stays aligned with the codebase.
