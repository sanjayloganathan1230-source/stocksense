from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get('/api/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok', 'service': 'StockSense API'}


def test_system_status_endpoint_does_not_expose_credentials():
    response = client.get('/api/system/status')

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "UPSTOX_ACCESS_TOKEN" not in response.text
    assert "UPSTOX_CLIENT_SECRET" not in response.text
