import pytest
from fastapi.testclient import TestClient
from sweepai.health import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "UP"
    assert "details" in data
    assert "sandbox" in data["details"]
    assert "mongodb" in data["details"]
    assert "redis" in data["details"]
    assert "system_resources" in data["details"]
    assert "cpu_usage" in data["details"]["system_resources"]
    assert "memory_usage" in data["details"]["system_resources"]
    assert "disk_usage" in data["details"]["system_resources"]
    assert "network_traffic" in data["details"]["system_resources"]
    assert "bytes_sent" in data["details"]["system_resources"]["network_traffic"]
    assert "bytes_received" in data["details"]["system_resources"]["network_traffic"]
