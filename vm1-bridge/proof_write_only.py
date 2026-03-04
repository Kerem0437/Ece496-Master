from influxdb_client import InfluxDBClient, Point
from influxdb_client.rest import ApiException
import os

URL=os.environ.get("INFLUX_URL","http://127.0.0.1:8086")
ORG=os.environ.get("INFLUX_ORG","ECE496")
BUCKET=os.environ.get("INFLUX_BUCKET","capstone")
TOKEN=os.environ.get("INFLUX_TOKEN","")

if not TOKEN:
    raise SystemExit("Missing INFLUX_TOKEN in env.")

c = InfluxDBClient(url=URL, token=TOKEN, org=ORG)

# write works
c.write_api().write(bucket=BUCKET, record=Point("auth_test").field("x", 1))
print("WRITE OK")

# read should fail for write-only tokens
try:
    c.query_api().query(f'from(bucket:"{BUCKET}") |> range(start:-5m)')
    print("READ UNEXPECTEDLY OK (token has read access)")
except ApiException as e:
    print("READ DENIED (expected for write-only):", e.status, e.reason)
