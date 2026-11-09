"""Bounded complete-frame broker exchange; no I/O, processes or network.

A future pipe transport must bound reads and implement deadline/cancellation.
Lengths cover UTF-8 JSON bytes, not characters, and include response metadata.
"""
import json
import struct

from app.core.skill_broker import MAX_REQUEST_FRAME_BYTES, MAX_RESULT_FRAME_BYTES

HEADER_BYTES = 4


class FrameError(ValueError):
    pass


def request_size(header: bytes) -> int:
    """Call before allocating/reading a request body from a future pipe."""
    if type(header) is not bytes or len(header) != HEADER_BYTES:
        raise FrameError('Invalid frame header')
    size = struct.unpack('!I', header)[0]
    if not 0 < size <= MAX_REQUEST_FRAME_BYTES:
        raise FrameError('Request frame size refused')
    return size


def _response(ok, data=None, truncated=False):
    # Failure detail stays in the trusted parent; never forward exceptions or
    # the authority's caller-supplied revocation reason to a child.
    return {'ok': ok, 'data': data, 'error': None if ok else 'Broker request refused',
            'truncated': truncated}


def _encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')


def encode_result(result) -> bytes:
    if not result.ok:
        payload = _encode(_response(False))
    elif not isinstance(result.data, str):
        payload = _encode(_response(False))
    else:
        # Bound before UTF-8/JSON allocation, including worst-case escaping.
        text = result.data[:MAX_RESULT_FRAME_BYTES]
        truncated = bool(result.truncated or len(text) < len(result.data))
        try:
            payload = _encode(_response(True, text, truncated))
            if len(payload) > MAX_RESULT_FRAME_BYTES:
                low, high = 0, len(text)
                while low < high:
                    middle = (low + high + 1) // 2
                    if len(_encode(_response(True, text[:middle], True))) <= MAX_RESULT_FRAME_BYTES:
                        low = middle
                    else:
                        high = middle - 1
                payload = _encode(_response(True, text[:low], True))
        except (UnicodeError, ValueError):
            payload = _encode(_response(False))
    return struct.pack('!I', len(payload)) + payload


def exchange(authority, frame: bytes) -> bytes:
    """Dispatch exactly one complete frame; invalid exchanges revoke authority."""
    from app.core.skill_broker import BrokerResult
    try:
        if type(frame) is not bytes or len(frame) < HEADER_BYTES:
            raise FrameError('Missing frame')
        size = request_size(frame[:HEADER_BYTES])
        if len(frame) != HEADER_BYTES + size:
            raise FrameError('Partial or trailing frame data')
        result = authority.dispatch_raw(frame[HEADER_BYTES:])
        if not result.ok:
            authority.revoke('protocol request refused')
        return encode_result(result)
    except Exception:
        authority.revoke('protocol exchange failed')
        return encode_result(BrokerResult(False))
