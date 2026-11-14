"""PostgreSQL backend that retries opening a connection while the server is briefly down.

unattended-upgrades restarts PostgreSQL when it upgrades it, which leaves the server
refusing connections (or "shutting down"/"starting up") for a few seconds. Without
this, every request that needs a new connection during that window fails with a 500.
Only opening a connection is retried, never a query, and only for errors that mean
the server is temporarily unavailable.
"""

import logging
import time

from django.db.backends.postgresql.base import Database
from django.db.backends.postgresql.base import DatabaseWrapper as PostgresDatabaseWrapper

logger = logging.getLogger(__name__)

# ~15s in total, which stays under the web server's 30s request timeout.
RETRY_DELAYS = (0.5, 1, 2, 4, 8)

TRANSIENT_ERRORS = (
    "connection refused",
    "the database system is shutting down",
    "the database system is starting up",
    "not yet accepting connections",
    "no such file or directory",  # The unix socket is gone while the server restarts.
)


def is_transient(error: Exception) -> bool:
    message = str(error).lower()
    return any(transient in message for transient in TRANSIENT_ERRORS)


class DatabaseWrapper(PostgresDatabaseWrapper):
    def get_new_connection(self, conn_params):
        for attempt, delay in enumerate(RETRY_DELAYS, start=1):
            try:
                return super().get_new_connection(conn_params)
            except Database.OperationalError as e:
                if not is_transient(e):
                    raise
                logger.warning(
                    "PostgreSQL is unavailable (attempt %d/%d), retrying in %ss: %s",
                    attempt,
                    len(RETRY_DELAYS) + 1,
                    delay,
                    e,
                )
                time.sleep(delay)
        return super().get_new_connection(conn_params)
