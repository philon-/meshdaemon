# Docker Deployment Guide

## Quick Start

### 1. Configure Environment

```bash
cp .env.example .env
# Edit .env with your deployment settings
nano .env
```

Key settings for your deployment:
- `MESHTASTIC_MCAST_GRP` and `MESHTASTIC_MCAST_PORT` — match your Meshtastic mesh network
- `MESHTASTIC_NODE_ID`, `MESHTASTIC_LONG_NAME`, `MESHTASTIC_SHORT_NAME` — node identity
- `VMA_GEOCODE` and `SMHI_GEOCODE` — alerts for your region

### 2. Build and Run

**Production:**
```bash
docker compose up -d
```

**Development:**
```bash
docker compose -f compose.yml -f compose.dev.yml up
```

Changes to files in `app/` are instantly visible in the container. No rebuild needed. Just restart the container if the app crashes or enable watch using --watch.

## Network Requirements

The app **must run with `network_mode: host`** to receive UDP multicast packets from the Meshtastic mesh:

- **Protocol:** UDP
- **Multicast Group:** 224.0.0.69 (configurable via `MESHTASTIC_MCAST_GRP`)
- **Port:** 4403 (configurable via `MESHTASTIC_MCAST_PORT`)

This means the container needs direct access to the host's network interfaces. The app will receive mesh packets from any Meshtastic device on the same LAN.

## File Reference

| File | Purpose |
|------|---------|
| `.env.example` | Template with all supported environment variables |
| `Dockerfile` | Container image build configuration |
| `compose.yml` | Production deployment configuration |
| `compose.dev.yml` | Development overrides (live code reload via volume mount) |

## Troubleshooting

### App doesn't receive multicast packets

1. Verify Meshtastic device is on the same network and set to UDP mode
2. Check firewall rules allow UDP 4403 on the host
3. Confirm `MESHTASTIC_MCAST_GRP` and `MESHTASTIC_MCAST_PORT` match your device configuration
4. Test connectivity: `docker exec meshdaemon_meshdaemon_1 python -c "import mudp; print('mudp available')"`

### Permission issues

The app runs as non-root user (uid 10001) for security. Multicast socket operations work fine as non-root. If you experience issues, verify:
- Host allows UDP multicast (not blocked by firewall rules)
- Network interface is accessible to the container (use `host` network mode)

### Viewing logs

```bash
docker-compose logs -f meshdaemon
```

### Health check

```bash
docker-compose ps
# or
docker exec meshdaemon_meshdaemon_1 pgrep -f "python.*app.main"
```
