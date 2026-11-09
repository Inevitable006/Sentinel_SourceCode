import pytest
from app.core.skill_broker import ParentBrokerAuthority


def authority(adapter=lambda target, args: 'ok', **kwargs):
    return ParentBrokerAuthority('synthetic', {'nested': {'value': 1}}, 'synthetic.txt', 'synthetic-request', 1, adapter, **kwargs)


@pytest.mark.parametrize('frame', [
    b'{"op": [], "seq": 1}', b'{"op": {}, "seq": 1}',
    b'{"op": "write", "op": "read", "seq": 1}',
    b'{"op": "read", "seq": NaN}', '\ud800',
    '[' * 2000 + ']' * 2000,
])
def test_malformed_protocol_fails_without_adapter(frame):
    broker = authority(lambda *a: pytest.fail('adapter called'))
    assert not broker.dispatch_raw(frame).ok


@pytest.mark.parametrize('seconds', [float('nan'), float('inf'), 0, -1, True])
def test_invalid_deadlines_rejected(seconds):
    with pytest.raises(ValueError):
        authority(deadline_seconds=seconds)


def test_adapter_cannot_mutate_authority_snapshot():
    def adapter(target, args):
        args['nested']['value'] = 99
        return 'ok'
    broker = authority(adapter)
    assert broker.dispatch({'op': 'read', 'seq': 1}).ok
    assert broker.approved_args['nested']['value'] == 1


def test_generation_change_permanently_invalidates_authority():
    broker = authority(lambda *a: pytest.fail('adapter called'))
    broker.update_generation(2)
    broker.update_generation(1)
    assert not broker.dispatch({'op': 'read', 'seq': 1}).ok


@pytest.mark.parametrize('output', ['\ud800', {'private': 'not text'}])
def test_invalid_adapter_output_fails_safely(output):
    assert not authority(lambda *a: output).dispatch({'op': 'read', 'seq': 1}).ok


def test_deadline_boundary_is_expired():
    now = [1.0]
    broker = authority(lambda *a: pytest.fail('adapter called'), deadline_seconds=1, clock=lambda: now[0])
    now[0] = 2
    assert not broker.dispatch({'op': 'read', 'seq': 1}).ok
