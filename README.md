# flask-observability
Add observability for your Flask app through InfluxDB



## Install

    $ pip install flask-observability
    
## Usage

### Automatically gather usage metrics

```python
from flask import Flask
from flask_observability import Observability

app = Flask("demo")
app.config["OBSERVE_AUTO_BIND_VIEWS"] = True
obs = Observability(app)

@app.route("/login", methods=["GET"])
def login():
    ...
 
 ```

By setting `OBSERVE_AUTO_BIND_VIEWS` to `True`, the extension will generate usage statistics 
for every call to a view, including logged-in user, status code and response time.

 
    $ influx -database demo
    Connected to http://localhost:8086 version v1.7.7
    InfluxDB shell version: v1.7.7
    > select * from views
    name: views
    time                2xx 4xx 5xx error host           http_response_code method response_time         result       status_code success user  view
    ----                --- --- --- ----- ----           ------------------ ------ -------------         ------       ----------- ------- ----  ----
    1562347284770242816 1                 guybrush.local 200                GET    0.04097118496429175   success      200         1             /api/swagger.json
    1562347285900697088     1       1     guybrush.local 401                POST   0.008022414986044168  client_error 401                       /api/auth
    1562347285977812992         1   1     guybrush.local 500                POST   0.027613310026936233  server_error 500                       /api/auth
    1562347286013081088     1       1     guybrush.local 401                POST   0.007381511037237942  client_error 401                       /api/auth
    1562347286060188160     1       1     guybrush.local 401                POST   0.007862744037993252  client_error 401                       /api/auth
    1562347286082478080     1       1     guybrush.local 401                POST   0.00800499296747148   client_error 401                       /api/auth
    1562347286106200832     1       1     guybrush.local 401                POST   0.004647177993319929  client_error 401                       /api/auth
    1562347286155630080     1       1     guybrush.local 401                POST   0.009268736001104116  client_error 401                       /api/auth
    1562347286181106944     1       1     guybrush.local 401                POST   0.008604614995419979  client_error 401                       /api/auth
    1562347286202841088     1       1     guybrush.local 401                POST   0.00504414492752403   client_error 401                       /api/auth
    1562347286252381184         1   1     guybrush.local 500                POST   0.030566500034183264  server_error 500                       /api/auth


### Send metrics manually

```python
from flask import Flask
from flask_observability import Observability, metrics

app = Flask("demo")
app.config['VERSION'] = "1.0.0"
obs = Observability(app)

with app.app_context():
    metrics.send("heartbeat", alive=True, 
                 tags={'version': app.config['VERSION']})

```

    $ influx -database demo
    Connected to http://localhost:8086 version v1.7.7
    InfluxDB shell version: v1.7.7
    Using database demo
    > select * from heartbeat
    name: heartbeat
    time                alive host           version
    ----                ----- ----           -------
    1562358967224788992 true  guybrush.local 1.0.0
