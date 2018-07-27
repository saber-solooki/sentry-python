from __future__ import absolute_import
from __future__ import print_function

import sys
import logging

from sentry_sdk import get_current_hub, capture_event, add_breadcrumb
from sentry_sdk.utils import to_string, Event, skip_internal_frames
from sentry_sdk.hub import _internal_exceptions

from . import Integration


class LoggingIntegration(Integration):
    identifier = "logging"

    def __init__(self, level=logging.INFO, event_level=None):
        self._handler = SentryHandler(level=level, event_level=event_level)

    def install(self, client):
        handler = self._handler

        old_callhandlers = logging.Logger.callHandlers

        def sentry_patched_callhandlers(self, record):
            handler.handle(record)
            return old_callhandlers(self, record)

        logging.Logger.callHandlers = sentry_patched_callhandlers


class SentryHandler(logging.Handler, object):
    def __init__(self, level, event_level):
        logging.Handler.__init__(self, level)
        if event_level is None:
            self._event_level = None
        else:
            self._event_level = logging._checkLevel(event_level)

    def emit(self, record):
        with _internal_exceptions():
            self.format(record)
            return self._emit(record)

    def can_record(self, record):
        return not record.name.startswith("sentry_sdk")

    def _breadcrumb_from_record(self, record):
        return {
            "ty": "log",
            "level": self._logging_to_event_level(record.levelname),
            "category": record.name,
            "message": record.message,
        }

    def _emit(self, record):
        add_breadcrumb(self._breadcrumb_from_record(record))

        if not self._should_create_event(record):
            return

        if not self.can_record(record):
            print(to_string(record.message), file=sys.stderr)
            return

        event = Event()

        # exc_info might be None or (None, None, None)
        if record.exc_info and all(record.exc_info):
            exc_type, exc_value, tb = record.exc_info
            event.set_exception(
                exc_type,
                exc_value,
                skip_internal_frames(tb),
                get_current_hub().client.options["with_locals"],
            )

        event["level"] = self._logging_to_event_level(record.levelname)
        event["logger"] = record.name

        event["logentry"] = {"message": to_string(record.msg), "params": record.args}

        capture_event(event)

    def _logging_to_event_level(self, levelname):
        return {"critical": "fatal"}.get(levelname.lower(), levelname.lower())

    def _should_create_event(self, record):
        return self._event_level is not None and record.levelno >= self._event_level
