"""ApiGatekeeper (PRD_7 §2.4, §3; PLAN.md ADR-4): the *sole* doorway
`infra/email_sender.py` and `infra/llm_provider.py` are allowed to be
called through. Routes every call through the book's own Figure 13 order
(p.74, ch.9.3.1) -- Quota Manager, then token-bucket + FIFO queue, then
the DOS detector -- then real retry/backoff on the way out; every attempt
logged, gate or no gate.

Quota Manager was previously missing entirely (Cop team review; the book's
own diagram independently confirms it's a real, named third gate, not
optional) -- `quota_manager` is opt-in (`None` = disabled) since the book
gives no concrete daily number to wire in by default (I6/I9: never invent
one). The token-bucket/DOS-detector check order was also silently reversed
from the book's own diagram before this fix; now matches it exactly.
"""

import time

from thief_peer.exceptions import ProviderError, RateLimitedError, TransportError
from thief_peer.shared.rate_limiter import DosDetector, QuotaManager, RequestQueue, TokenBucket


class ApiGatekeeper:
    def __init__(
        self,
        token_bucket: TokenBucket,
        dos_detector: DosDetector,
        queue: RequestQueue,
        quota_manager: QuotaManager | None = None,
        max_retries: int = 3,
        backoff_sec: float = 5.0,
        poll_interval_sec: float = 0.1,
        max_poll_attempts: int = 50,
    ):
        self._token_bucket = token_bucket
        self._dos_detector = dos_detector
        self._queue = queue
        self._quota_manager = quota_manager
        self._max_retries = max_retries
        self._backoff_sec = backoff_sec
        self._poll_interval_sec = poll_interval_sec
        self._max_poll_attempts = max_poll_attempts
        self.call_log: list[dict] = []

    def execute(self, api_call, *args, **kwargs):
        if self._quota_manager is not None and not self._quota_manager.allow():
            self._log("rejected_quota_exhausted")
            raise TransportError("Gatekeeper locked: daily quota exhausted")

        if not self._wait_for_token():
            self._log("rejected_queue_full")
            raise TransportError("Gatekeeper request queue is full; call rejected")

        if self._dos_detector.is_locked:
            self._log("rejected_dos_lock")
            raise TransportError("Gatekeeper locked: anomalous call volume detected")

        self._dos_detector.record_call()
        if self._dos_detector.is_locked:
            self._log("rejected_dos_lock")
            raise TransportError("Gatekeeper locked: anomalous call volume detected")

        return self._call_with_retry(api_call, args, kwargs)

    def _wait_for_token(self) -> bool:
        if self._token_bucket.allow():
            return True
        if not self._queue.enqueue(object()):
            return False
        try:
            for _ in range(self._max_poll_attempts):
                time.sleep(self._poll_interval_sec)
                if self._token_bucket.allow():
                    return True
            return False
        finally:
            self._queue.dequeue()

    def _call_with_retry(self, api_call, args, kwargs):
        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                result = api_call(*args, **kwargs)
                self._log("success")
                return result
            except RateLimitedError as exc:
                last_error = exc
                if attempt < self._max_retries:
                    self._log("retry_rate_limited")
                    time.sleep(self._backoff_sec * attempt)
            except Exception as exc:
                last_error = exc
                if attempt < 2:  # other transient failures: retry once, no more
                    self._log("retry_transient")
                    continue
                break

        self._log("failed")
        raise ProviderError(f"Gatekeeper call failed after retries: {last_error}")

    def _log(self, outcome: str) -> None:
        self.call_log.append({"outcome": outcome, "timestamp": time.time()})
