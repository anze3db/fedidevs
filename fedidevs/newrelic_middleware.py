"""Dramatiq middleware to initialize New Relic in worker processes."""

import dramatiq
import newrelic.agent


class NewRelicMiddleware(dramatiq.Middleware):
    """Middleware that initializes New Relic agent in each worker process."""

    def __init__(self):
        self._initialized = False

    def before_worker_boot(self, broker, worker):
        """Called when a worker process starts, before it begins processing messages."""
        if not self._initialized:
            newrelic.agent.initialize()
            newrelic.agent.register_application(timeout=10.0)
            self._initialized = True
