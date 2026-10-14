import logging
from contextlib import contextmanager
from time import perf_counter

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.domain.errors import IngestionBusy, ProviderError

log = logging.getLogger(__name__)


def client(service: str, region: str, session=None):
    return (session or boto3).client(
        service,
        region_name=region,
        config=Config(
            retries={"mode": "standard", "total_max_attempts": 4}, connect_timeout=5, read_timeout=90
        ),
    )


@contextmanager
def aws_operation(operation: str, conflict_is_busy: bool = False):
    start = perf_counter()
    try:
        yield
    except (BotoCoreError, ClientError) as exc:
        log.warning(
            "provider_operation_failed", extra={"operation": operation, "error_type": type(exc).__name__}
        )
        if (
            conflict_is_busy
            and isinstance(exc, ClientError)
            and exc.response["Error"]["Code"] == "ConflictException"
        ):
            raise IngestionBusy() from exc
        raise ProviderError() from exc
    finally:
        log.info(
            "provider_operation",
            extra={"operation": operation, "latency_ms": int((perf_counter() - start) * 1000)},
        )
