import json
import os
import sys
import pytest

# Ensure project root in path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from widget_server import app


@pytest.fixture(scope="module")
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def test_health_endpoint(client):
    resp = client.get('/health')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data and data.get('status') == 'healthy'


def test_ollama_status_endpoint(client):
    resp = client.get('/ollama/status')
    # Either connected or error (but endpoint should respond)
    assert resp.status_code in (200, 500)
    data = resp.get_json()
    assert 'status' in data


def test_chat_endpoint_requires_message(client):
    resp = client.post('/chat', json={})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data.get('status') == 'error'


def test_chat_endpoint_basic_flow(client):
    payload = {"message": "Привет, расскажи о клинике", "session_id": "smoke-test"}
    resp = client.post('/chat', json=payload)
    # Should return 200 even if falling back
    assert resp.status_code in (200, 500)
    if resp.status_code == 200:
        data = resp.get_json()
        assert 'response' in data
        assert 'session_id' in data
    else:
        # If 500, ensure structured error
        data = resp.get_json()
        assert data.get('status') == 'error'