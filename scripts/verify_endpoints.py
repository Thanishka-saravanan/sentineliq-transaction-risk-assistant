import json
import urllib.error
import urllib.request

base = "http://localhost:8000"

endpoints = [
    ("/api/health", 200),
    ("/", 200),
    ("/api/customers", 200),
    ("/api/customers/CUST001", 200),
    ("/api/customers/CUST001/transactions", 200),
    ("/api/rules", 200),
    ("/api/customers/CUST001/baseline", 200),
    ("/api/customers/CUST001/baseline/summary", 200),
    ("/api/customers/INVALID999/baseline", 404),
    ("/api/customers/INVALID999/baseline/summary", 404),
]

all_passed = True

for path, expected_code in endpoints:
    url = base + path
    try:
        resp = urllib.request.urlopen(url)
        data = resp.read().decode("utf-8")
        status = resp.status
        print(f"SUCCESS [{status}] {path}")
        if "summary" in path and status == 200:
            parsed = json.loads(data)
            print(f"   Summary: {parsed}")
    except urllib.error.HTTPError as e:
        status = e.code
        data = e.read().decode("utf-8")
        if status == expected_code:
            print(f"EXPECTED [{status}] {path} -> {data.strip()}")
        else:
            print(f"FAILED [{status}] {path} (expected {expected_code})")
            all_passed = False

if all_passed:
    print("\nALL LIVE ENDPOINTS VERIFIED SUCCESSFULLY!")
else:
    raise SystemExit("Endpoint verification failed!")
