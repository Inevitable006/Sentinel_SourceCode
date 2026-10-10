"""Step 1.5: secrets never appear in printed or logged text."""
import io
import logging

from app.core import redaction


def test_session_tokens_raw_keys_and_recovery_keys_are_masked():
    token = "a" * 32 + "0123456789abcdef" * 2
    raw_key = "x'" + "ab" * 32 + "'"
    rk = "ABCD-EFGH-IJKL-MNOP-QRST-UVWX-YZ23-4567"
    out = redaction.redact(f"t={token} key={raw_key} rk={rk} url=/ws?token=abc123 password=hunter22")
    assert token not in out and raw_key not in out and rk not in out
    assert "abc123" not in out and "hunter22" not in out


def test_registered_secret_values_are_masked():
    redaction.register("sk-live-5ecret-value-99")
    try:
        assert "sk-live-5ecret-value-99" not in redaction.redact("calling api with sk-live-5ecret-value-99 now")
    finally:
        redaction.unregister("sk-live-5ecret-value-99")


def test_short_values_are_not_registered():
    redaction.register("abc")
    assert redaction.redact("abc abc") == "abc abc"


def test_stream_wrapper_and_logging_filter():
    buf = io.StringIO()
    stream = redaction.RedactingStream(buf)
    stream.write("token=" + "f" * 64 + "\n")
    assert "f" * 64 not in buf.getvalue()

    # plain messages: the filter redacts them
    log_buf = io.StringIO()
    logger = logging.getLogger("sentinel.test.redaction")
    handler = logging.StreamHandler(log_buf)
    handler.addFilter(redaction.RedactingFilter())
    logger.addHandler(handler)
    try:
        logger.warning("key is x'" + "cd" * 32 + "'")
    finally:
        logger.removeHandler(handler)
    assert "cd" * 32 not in log_buf.getvalue()


def test_records_with_arguments_stay_formattable_and_are_redacted_at_the_stream():
    """uvicorn's access formatter needs record.args; the stream under the handler does the redacting."""
    out = io.StringIO()
    logger = logging.getLogger("sentinel.test.redaction.args")
    handler = logging.StreamHandler(redaction.RedactingStream(out))
    handler.addFilter(redaction.RedactingFilter())
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    try:
        logger.warning('%s - "%s %s" %d', "127.0.0.1:5000", "GET", "/ws?token=" + "e" * 64, 200)
    finally:
        logger.removeHandler(handler)
    text = out.getvalue()
    assert "127.0.0.1:5000" in text and "GET" in text and "e" * 64 not in text
    assert "Logging error" not in text
