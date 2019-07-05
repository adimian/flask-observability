import datetime
import logging
import socket
from collections import defaultdict
from functools import wraps
from pprint import pformat
from time import perf_counter

import influxdb
import pytz
from flask import _request_ctx_stack, current_app, request, g
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
        app.config.setdefault("INFLUXDB_DATABASE", app.import_name)
        app.config.setdefault("INFLUXDB_SSL", False)
        app.config.setdefault("INFLUXDB_VERIFY_SSL", False)
        app.config.setdefault("INFLUXDB_TIMEOUT", None)
        app.config.setdefault("INFLUXDB_RETRIES", 3)
        app.config.setdefault("INFLUXDB_USE_UDP", False)
        app.config.setdefault("INFLUXDB_UDP_PORT", 4444)
        app.config.setdefault("INFLUXDB_PROXIES", None)
        app.config.setdefault("INFLUXDB_POOL_SIZE", 10)
        app.config.setdefault("INFLUXDB_PATH", "")

        app.before_request(self._before_request)
        app.after_request(self._after_request)

        logger.debug("observability configured")

    def _before_request(self):
        g._request_start = perf_counter()

    def _after_request(self, response):
        fields = {}
        tags = {
            "view": request.environ["REQUEST_URI"],
            "method": request.method,
        }

        if isinstance(response.status_code, int):
            status_code = response.status_code
        else:
            status_code = response.status_code.value

        tags["status_code"] = str(status_code)
        fields["http_response_code"] = status_code

        if 200 <= status_code < 300:
            tags["result"] = "success"
            fields["success"] = 1
        else:
            tags["result"] = "error"
            fields["success"] = 0
        metrics.observe_view(fields=fields, tags=tags)

        return response

    def _client(self):
        client = influxdb.InfluxDBClient(
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

        logger.debug("influxdb client configured")
        return client

    def request_user(self):
        try:
            from flask_login import current_user
        except ImportError:
            return

        for attr in self.USUAL_NAME_ATTRS:
            identity = getattr(current_user, attr, None)
            if identity:
                logger.debug("observability user: {}".format(identity))
                return identity

        return str(current_user)

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

    def observe_view(self, fields, tags):
        message = self.base_message(measurement="views")

        fields["response_time"] = perf_counter() - g._request_start

        message["fields"].update(fields)
        message["tags"].update(tags)

        if self.testing:
            logger.debug(
                "observability in testing mode, collecting message only"
            )
            self.outgoing["views"].append(message)
        else:
            logger.debug(
                "observability in live mode, sending {}".format(
                    pformat(message)
                )
            )
            self.client.write_points([message])
