import pytest
from flask import Flask, request, abort, make_response
from freezegun import freeze_time

from flask_observability import Observability, metrics


@pytest.fixture
def app():
    app = Flask("demo")
    app.config["TESTING"] = True
    obs = Observability(hostname="somehost")
    obs.init_app(app)

    @app.route("/login", methods=["GET"])
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
        "fields": {
            "2xx": 1,
            "http_response_code": 200,
            "response_time": observation["fields"]["response_time"],
            "success": 1,
        },
        "measurement": "views",
        "tags": {
            "host": "somehost",
            "method": "GET",
            "result": "success",
            "status_code": "200",
            "view": "/login",
        },
        "time": "2012-08-26T00:00:00+00:00",
    }


@freeze_time("2012-08-26")
def test_metrics_spot_failure(app):
    client = app.test_client()

    res = client.get("/login", data={"username": "bad"})
    assert res.status_code == 403

    assert len(metrics.outgoing["views"]) == 1

    observation = metrics.outgoing["views"][0]

    assert observation["fields"]["4xx"] == 1
    assert observation["fields"]["error"] == 1
    assert observation["fields"]["http_response_code"] == 403


@freeze_time("2012-08-26")
def test_metrics_can_be_sent_manually(app):
    metrics.send(
        measurement="heartbeat", alive=True, tags={"trigger": "manual"}
    )

    observation = metrics.outgoing["heartbeat"][0]
    assert observation["fields"]["alive"] is True
    assert observation["tags"]["trigger"] == "manual"
