import pytest
from flask import Flask, request, abort, make_response
from freezegun import freeze_time

from flask_observability import Observability, metrics, observe


@pytest.fixture
def app():
    app = Flask("demo")
    app.config["TESTING"] = True
    obs = Observability(hostname="somehost")
    obs.init_app(app)

    @app.route("/login", methods=["GET"])
    @observe("login")
    def login():
        if request.form.get("username") == "bad":
            abort(403)
        return make_response("", 200)

    with app.app_context():
        yield app


@freeze_time("2012-08-26")
def test_metrics_spot_success(app):
    client = app.test_client()

    res = client.get("/login", data={"username": "admin"})
    assert res.status_code == 200

    assert len(metrics.outgoing["views"]) == 1

    observation = metrics.outgoing["views"][0]

    assert observation == {
        "measurement": "views",
        "time": "2012-08-26T00:00:00+00:00",
        "tags": {
            "host": "somehost",
            "view": "login",
            "method": "GET",
            "result": "success",
            "status_code": "200",
        },
        "fields": {
            "http_response_code": 200,
            "success": 1,
            "response_time": observation["fields"]["response_time"],
        },
    }


@freeze_time("2012-08-26")
def test_metrics_spot_failure(app):
    client = app.test_client()

    res = client.get("/login", data={"username": "bad"})
    assert res.status_code == 403

    assert len(metrics.outgoing["views"]) == 1

    observation = metrics.outgoing["views"][0]

    assert observation["fields"]["success"] == 0
    assert observation["fields"]["http_response_code"] == 403
