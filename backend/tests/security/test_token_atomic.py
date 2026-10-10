"""F10: one token, many simultaneous presenters -> exactly one success."""
import threading
import time

from app.core.token_service import token_service


def _race(token, threads=16, args=None):
    barrier = threading.Barrier(threads)
    wins = []
    def attempt():
        barrier.wait()
        if token_service.validate_token(token, "race", "t", args or {"x": 1}):
            wins.append(1)
    workers = [threading.Thread(target=attempt) for _ in range(threads)]
    for w in workers: w.start()
    for w in workers: w.join()
    return len(wins)


def test_concurrent_replay_executes_once():
    for _ in range(50):
        token = token_service.generate_token("race", "t", {"x": 1}, 3)
        assert _race(token) == 1


def test_revocation_racing_validation_never_double_spends():
    for _ in range(50):
        token = token_service.generate_token("race", "t", {"x": 1}, 3)
        revoker = threading.Thread(target=token_service.revoke_session, args=("race",))
        revoker.start()
        wins = _race(token, threads=4)
        revoker.join()
        assert wins <= 1
        assert not token_service.validate_token(token, "race", "t", {"x": 1})


def test_expired_and_mismatched_tokens_fail():
    token = token_service.generate_token("race", "t", {"x": 1}, 3, expiry_seconds=0)
    time.sleep(0.01)
    assert _race(token) == 0
    token = token_service.generate_token("race", "t", {"x": 1}, 3)
    assert not token_service.validate_token(token, "race", "t", {"x": 2})
    assert not token_service.validate_token(token, "other", "t", {"x": 1})
