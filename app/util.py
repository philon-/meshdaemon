from __future__ import annotations
import zlib
from . import config


def _utf8_prefix(text: str, max_bytes: int) -> tuple[str, str]:
    if max_bytes <= 0 or not text:
        return "", text

    used = 0
    split_at = 0
    for idx, char in enumerate(text):
        char_len = len(char.encode("utf-8"))
        if used + char_len > max_bytes:
            break
        used += char_len
        split_at = idx + 1

    return text[:split_at], text[split_at:]


def truncate_utf8(s: str) -> list[str]:
    """
    Split a string into Meshtastic-sized chunks, each fitting within
    MESHTASTIC_MAX_BYTES. Chunks are suffixed with " i/N" numbering.
    If the whole string fits in one message, it is returned as-is (no suffix).
    Returns an empty list if MESHTASTIC_MAX_MESSAGES < 1 or the string is empty.
    """
    s = s.strip()
    if config.MESHTASTIC_MAX_MESSAGES < 1 or not s:
        return []

    # Fast path: already fits in a single message, no suffix needed
    if len(s.encode("utf-8")) <= config.MESHTASTIC_MAX_BYTES:
        return [s]

    words = s.split()

    # Reserve worst-case space for " N/N" suffix and optional " [...]" ellipsis
    suffix_bytes = len(f" {config.MESHTASTIC_MAX_MESSAGES}/{config.MESHTASTIC_MAX_MESSAGES}".encode("utf-8"))
    ellipsis = " [...]"
    ellipsis_bytes = len(ellipsis.encode("utf-8"))

    chunks: list[str] = []
    i = 0

    for chunk_idx in range(config.MESHTASTIC_MAX_MESSAGES):
        is_last = chunk_idx == config.MESHTASTIC_MAX_MESSAGES - 1

        limit = max(0, config.MESHTASTIC_MAX_BYTES - suffix_bytes - (ellipsis_bytes if is_last else 0))

        cur_words: list[str] = []
        cur_bytes = 0

        while i < len(words):
            w = words[i]
            add = len(w.encode("utf-8")) + (0 if not cur_words else 1)
            if cur_bytes + add <= limit:
                cur_words.append(w)
                cur_bytes += add
                i += 1
            else:
                break

        if not cur_words and i < len(words) and limit > 0:
            head, tail = _utf8_prefix(words[i], limit)
            if head:
                cur_words.append(head)
                if tail:
                    words[i] = tail
                else:
                    i += 1

        if is_last and i < len(words):
            if cur_words:
                chunk_text = " ".join(cur_words) + ellipsis
            elif limit > 0:
                # Nothing fit — squeeze a UTF-8-safe partial word so the user sees something
                partial = words[i].encode("utf-8")[:limit].decode("utf-8", "ignore")
                chunk_text = (partial + ellipsis).strip()
            else:
                chunk_text = ellipsis.strip()
        else:
            chunk_text = " ".join(cur_words)

        if not chunk_text and not is_last:
            break

        chunks.append(chunk_text)

        if i >= len(words):
            break

    total = len(chunks)
    for idx in range(total):
        chunks[idx] = chunks[idx].strip() + f" {idx + 1}/{total}"

    return chunks

def make_message_id(s: str) -> int:
    """Generate a deterministic 32-bit Meshtastic packet ID from a string."""
    return zlib.crc32(s.encode("utf-8")) & 0xFFFFFFFF