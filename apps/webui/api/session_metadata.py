"""Helpers for partial reads of session JSON metadata."""
import json


REQUIRED_SESSION_METADATA_KEYS = frozenset({
    'session_id',
    'title',
    'created_at',
    'updated_at',
})


def find_top_level_json_key(text, key):
    """Return the byte offset of a top-level JSON object key, if present."""
    depth = 0
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == '"':
            start = i
            i += 1
            escaped = False
            chars = []
            while i < n:
                c = text[i]
                if escaped:
                    chars.append(c)
                    escaped = False
                elif c == '\\':
                    escaped = True
                elif c == '"':
                    break
                else:
                    chars.append(c)
                i += 1
            if i >= n:
                return None
            if depth == 1 and ''.join(chars) == key:
                j = i + 1
                while j < n and text[j] in ' \t\r\n':
                    j += 1
                if j < n and text[j] == ':':
                    return start
        elif ch in '{[':
            depth += 1
        elif ch in '}]':
            depth -= 1
        i += 1
    return None


def read_metadata_json_prefix(path, max_prefix_bytes=65536):
    """Read only the metadata portion before the top-level messages array."""
    buf = ''
    with open(path, 'r', encoding='utf-8') as f:
        while len(buf.encode('utf-8')) < max_prefix_bytes:
            chunk = f.read(4096)
            if not chunk:
                return None
            buf += chunk
            messages_pos = find_top_level_json_key(buf, 'messages')
            if messages_pos is None:
                continue
            prefix = buf[:messages_pos].rstrip()
            if prefix.endswith(','):
                prefix = prefix[:-1].rstrip()
            return f'{prefix}\n}}'
    return None


def read_session_metadata_payload(path, *, max_prefix_bytes=65536):
    """Return a metadata-only session payload or None if full load is needed."""
    prefix = read_metadata_json_prefix(path, max_prefix_bytes=max_prefix_bytes)
    if not prefix:
        return None
    parsed = json.loads(prefix)
    if not REQUIRED_SESSION_METADATA_KEYS.issubset(parsed.keys()):
        return None
    parsed['messages'] = []
    parsed['tool_calls'] = []
    return parsed
