import datetime
import logging
import socket
from collections import defaultdict
from functools import wraps

import influxdb
import pytz
from flask import _request_ctx_stack, current_app
from werkzeug.local import LocalProxy

logger = logging.getLogger(__name__)

metrics = LocalProxy(lambda: _get_metrics())


def _get_metrics():
    return current_app.observability


class Observability:
    USUAL_NAME_ATTRS = ("name", "username", "login", "uid", "id")

    def __init__(self, app=None, hostname=None):
        self.hostname = hostname or socket.gethostname()
        self.app = app

        if app is not None:
            self.init_app(app)

        self.outgoing = defaultdict(list)

    def init_app(self, app):
        self.app = app
        app.observability = self

        app.config.setdefault("INFLUXDB_HOST", "localhost")
        app.config.setdefault("INFLUXDB_PORT", "8086")
        app.config.setdefault("INFLUXDB_USER", "root")
        app.config.setdefault("INFLUXDB_PASSWORD", "root")
        app.config.setdefault("INFLUXDB_DATABASE", None)
        app.config.setdefault("INFLUXDB_SSL", False)
        app.config.setdefault("INFLUXDB_VERIFY_SSL", False)
        app.config.setdefault("INFLUXDB_TIMEOUT", None)
        app.config.setdefault("INFLUXDB_RETRIES", 3)
        app.config.setdefault("INFLUXDB_USE_UDP", False)
        app.config.setdefault("INFLUXDB_UDP_PORT", 4444)
        app.config.setdefault("INFLUXDB_PROXIES", None)
        app.config.setdefault("INFLUXDB_POOL_SIZE", 10)
        app.config.setdefault("INFLUXDB_PATH", "")

    def _client(self):
        return influxdb.InfluxDBClient(
            host=current_app.config["INFLUXDB_HOST"],
            port=current_app.config["INFLUXDB_PORT"],
            username=current_app.config["INFLUXDB_USER"],
            password=current_app.config["INFLUXDB_PASSWORD"],
            database=current_app.config["INFLUXDB_DATABASE"],
            ssl=current_app.config["INFLUXDB_SSL"],
            timeout=current_app.config["INFLUXDB_TIMEOUT"],
            verify_ssl=current_app.config["INFLUXDB_VERIFY_SSL"],
            retries=current_app.config["INFLUXDB_RETRIES"],
            use_udp=current_app.config["INFLUXDB_USE_UDP"],
            udp_port=current_app.config["INFLUXDB_UDP_PORT"],
            proxies=current_app.config["INFLUXDB_PROXIES"],
            pool_size=current_app.config["INFLUXDB_POOL_SIZE"],
        )

    def request_user(self):
        try:
            from flask_login import current_user
        except ImportError:
            return

        for attr in self.USUAL_NAME_ATTRS:
            identity = getattr(current_user, attr, None)
            if identity:
                return identity

    @property
    def testing(self):
        return current_app.config.get("TESTING")

    @property
    def now(self):
        return datetime.datetime.now(tz=pytz.utc)

    @property
    def client(self):
        if not self.app.config["TESTING"]:
            ctx = _request_ctx_stack.top
            if ctx is not None:
                if not hasattr(ctx, "influxdb_client"):
                    ctx.influxdb_client = self._client()
                return ctx.influxdb_client

    def base_message(self, measurement):
        message = {
            "measurement": measurement,
            "time": self.now.isoformat(),
            "tags": {"host": self.hostname},
            "fields": {},
        }

        identity = self.request_user()
        if identity:
            message["user"] = identity

        return message

    def observe_view(self, view, fields, tags):
        measurement = view.__name__

        message = self.base_message(measurement=measurement)
        message["fields"].update(fields)
        message["tags"].update(tags)

        if self.testing:
            self.outgoing[view.__name__].append(message)
        else:
            self.client.write_points([message])


def observe(f):
    @wraps(f)
    def wrapper(*args, **kwds):
        fields = {}
        tags = {}
        try:
            result = f(*args, **kwds)
            fields["success"] = 1
            tags["code"] = str(result.status_code)
            metrics.observe_view(f, fields=fields, tags=tags)
            return result
        except Exception as exc:
            fields["failure"] = 1
            code = getattr(exc, "code", None)
            if code:
                tags["code"] = str(code)
            metrics.observe_view(f, fields=fields, tags=tags)
            raise

    return wrapper
