import tenacity
import traceback
import logging

import requests
from tenacity import retry as _tenacity_retry, retry_if_exception
from utils.control_exceptions import is_retryable_agent_error


agent_retry_policy = retry_if_exception(is_retryable_agent_error)


def retry(*args, **kwargs):
    """Tenacity retry with ViMax budget/deadline/cancellation fail-fast policy."""
    kwargs.setdefault("retry", agent_retry_policy)
    return _tenacity_retry(*args, **kwargs)

def after_func(retry_state: tenacity.RetryCallState) -> None:
    if retry_state.outcome.failed:
        exc = retry_state.outcome.exception()
        logging.warning(f"Retrying {retry_state.fn.__name__} due to {repr(exc)} (Attempt {retry_state.attempt_number})")
        logging.debug(traceback.format_exception(type(exc), exc, exc.__traceback__))


def is_retryable_download_error(exc: BaseException) -> bool:
    """Network errors and 5xx responses are retryable; other HTTP errors (expired
    or invalid URLs, auth failures) will never succeed and must fail fast."""
    if isinstance(exc, requests.HTTPError):
        response = exc.response
        return response is None or response.status_code >= 500
    return isinstance(exc, requests.RequestException)


download_retry = tenacity.retry(
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(multiplier=1, max=10),
    retry=tenacity.retry_if_exception(is_retryable_download_error),
    after=after_func,
    reraise=True,
)
