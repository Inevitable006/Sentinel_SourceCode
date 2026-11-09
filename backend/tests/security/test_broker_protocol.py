import json
import struct

import pytest

from app.core.broker_protocol import exchange, encode_result, request_size, FrameError
from app.core.skill_broker import ParentBrokerAuthority, BrokerResult, MAX_RESULT_FRAME_BYTES


def frame(body):
    return struct.pack('!I', len(body)) + body


def unpack(data):
    size = struct.unpack('!I', data[:4])[0]
    assert size == len(data) - 4
    assert size <= MAX_RESULT_FRAME_BYTES
    return json.loads(data[4:])


def make_authority(adapter):
    return ParentBrokerAuthority('synthetic', {}, 'synthetic.txt', 'synthetic-request', 0, adapter)


def test_valid_exchange_and_replay():
    calls = []
    authority = make_authority(lambda *args: calls.append(args) or 'hello')
    request = frame(b'{"op":"read","seq":1}')
    assert unpack(exchange(authority, request))['data'] == 'hello'
    assert not unpack(exchange(authority, request))['ok']
    assert len(calls) == 1 and authority.is_revoked


@pytest.mark.parametrize('wire_frame', [b'', b'abc', frame(b''), struct.pack('!I', 8193),
    struct.pack('!I', 4294967295), frame(b'{}') + b'extra', struct.pack('!I', 5) + b'{}',
    frame(b'{"op":[],"seq":1}'), frame(b'{"op":"read","seq":1,"target":"different"}')])
def test_bad_frame_never_invokes_adapter_and_revokes(wire_frame):
    authority = make_authority(lambda *args: pytest.fail('adapter called'))
    result = unpack(exchange(authority, wire_frame))
    assert not result['ok'] and authority.is_revoked
    assert result['error'] == 'Broker request refused'


@pytest.mark.parametrize('text', ['a' * 20000, '\x00' * 20000, '😀' * 20000, '"\\\n' * 10000],
                         ids=['ascii', 'control-escaping', 'multibyte', 'json-escaping'])
def test_response_limit_includes_utf8_json_escaping_and_metadata(text):
    result = unpack(encode_result(BrokerResult(True, data=text)))
    assert result['ok'] and result['truncated']
    assert text.startswith(result['data'])


def test_private_revocation_reason_is_not_serialized():
    authority = make_authority(lambda *args: pytest.fail('adapter called'))
    authority.revoke('synthetic-private-marker')
    result = exchange(authority, frame(b'{"op":"read","seq":1}'))
    assert b'synthetic-private-marker' not in result
    assert not unpack(result)['ok']


def test_header_is_checked_before_body_allocation():
    assert request_size(struct.pack('!I', 8192)) == 8192
    with pytest.raises(FrameError):
        request_size(struct.pack('!I', 8193))
