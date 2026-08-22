import http.client
import os
import sys


def check_health():
    port = os.getenv("SERVICE_PORT", "8000")
    host = "localhost"
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request("GET", "/health")
        response = conn.getresponse()
        if 200 <= response.status < 300:
            sys.exit(0)
        else:
            print(f"Health check failed with status: {response.status}")
            sys.exit(1)
    except Exception as e:
        print(f"Health check failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    check_health()
