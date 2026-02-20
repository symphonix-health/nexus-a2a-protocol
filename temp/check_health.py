import json
import urllib.request

ports = {
    "triage": 8030,
    "diagnostics": 8031,
    "specialist": 8032,
    "treatment": 8033,
    "discharge": 8034,
    "pharmacy": 8035,
    "billing": 8036,
    "home-visit": 8037,
    "ccm": 8038,
    "avatar": 8039,
    "backend": 8099,
    "gateway": 8100,
}
for name, port in ports.items():
    try:
        r = urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3)
        d = json.loads(r.read())
        print(f"  {name:14s} :{port}  {d.get('status', '?')}")
    except Exception as e:
        short = str(e).split(":")[-1].strip() if ":" in str(e) else str(e)
        print(f"  {name:14s} :{port}  DOWN ({short})")
