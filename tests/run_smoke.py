import os
import sys
import json

# Ensure project root is on path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from widget_server import app


def main():
    app.config['TESTING'] = True
    print("Starting Flask test client smoke test...")
    with app.test_client() as client:
        print("GET /health")
        r = client.get('/health')
        print("Status:", r.status_code)
        try:
            print("Body:", r.get_json())
        except Exception:
            print("Body(raw):", r.data.decode('utf-8', errors='ignore'))

        print("\nGET /ollama/status")
        r = client.get('/ollama/status')
        print("Status:", r.status_code)
        try:
            print("Body:", r.get_json())
        except Exception:
            print("Body(raw):", r.data.decode('utf-8', errors='ignore'))

        print("\nPOST /chat (missing message)")
        r = client.post('/chat', json={})
        print("Status:", r.status_code)
        print("Body:", r.get_json())

        print("\nPOST /chat (basic)")
        payload = {"message": "Привет, расскажи о клинике", "session_id": "smoke-test"}
        r = client.post('/chat', json=payload)
        print("Status:", r.status_code)
        try:
            print("Body:", r.get_json())
        except Exception:
            print("Body(raw):", r.data.decode('utf-8', errors='ignore'))


if __name__ == '__main__':
    main()