from __future__ import annotations
from . import config

def truncate_utf8(s: str) -> list[str]:
    if config.MESHTASTIC_MAX_MESSAGES < 1:
        return []
    
    # If our string is already shorter than 200 bytes, do nothing 
    if len(s.encode('utf-8')) <= config.MESHTASTIC_MAX_BYTES: 
        return [s]


    words = s.split()
    if not words:
        return []

    # Worst-case suffix: space + max digits for both numbers (" 10/10", etc.)
    suffix_bytes = len(f" {config.MESHTASTIC_MAX_MESSAGES}/{config.MESHTASTIC_MAX_MESSAGES}".encode("utf-8"))
    ellipsis = " [...]"
    ellipsis_bytes = len(ellipsis.encode("utf-8"))

    chunks: list[str] = []
    i = 0  # index into words

    for chunk_idx in range(config.MESHTASTIC_MAX_MESSAGES):
        is_last = (chunk_idx == config.MESHTASTIC_MAX_MESSAGES - 1)

        reserve = suffix_bytes + (ellipsis_bytes if is_last else 0)
        limit = max(0, config.MESHTASTIC_MAX_BYTES - reserve)

        cur_words: list[str] = []
        cur_bytes = 0  # content bytes (no suffix included)

        while i < len(words):
            w = words[i]
            wb = len(w.encode("utf-8"))
            # bytes to add: the word plus a leading space if it's not the first in the chunk
            add = wb if not cur_words else 1 + wb

            if cur_bytes + add <= limit:
                cur_words.append(w)
                cur_bytes += add
                i += 1
            else:
                break

        # If we didn't consume all words and we're on the last chunk, add the ellipsis (fits by construction).
        if is_last and i < len(words):
            if cur_words:
                chunk_text = " ".join(cur_words) + ellipsis
            else:
                # Edge-case: nothing fit; try to squeeze a partial word so the user sees *something*
                # (maintain valid UTF-8 by decoding with 'ignore').
                next_w_bytes = words[i].encode("utf-8")
                # We'll use as much as will fit in the (limit) bytes — ellipsis already reserved.
                if limit > 0:
                    partial = next_w_bytes[:limit].decode("utf-8", "ignore")
                    chunk_text = (partial + ellipsis).strip()
                else:
                    # No room at all besides suffix/ellipsis: just return the ellipsis marker.
                    chunk_text = ellipsis.strip()
        else:
            chunk_text = " ".join(cur_words)

        # If nothing was added to this chunk (and it's not the last chance), stop.
        if not chunk_text and not is_last:
            break

        chunks.append(chunk_text)

        # If we consumed everything, we're done (no need to emit empty trailing chunks).
        if i >= len(words):
            break

    # Add " i/N" numbering to emitted chunks
    total = len(chunks)
    for idx in range(total):
        chunks[idx] = chunks[idx].strip() + f" {idx + 1}/{total}"

    return chunks