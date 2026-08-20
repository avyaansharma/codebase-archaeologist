import pytest
from fastapi.testclient import TestClient
from archaeologist.web.server import app

client = TestClient(app)

def test_get_repositories():
    response = client.get("/api/repos")
    assert response.status_code == 200
    data = response.json()
    assert "repositories" in data
    repo_ids = [r["id"] for r in data["repositories"]]
    assert "requests" in repo_ids
    assert "flask" in repo_ids
    assert "mss" in repo_ids

def test_get_repository_details():
    response = client.get("/api/repos/flask")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "pallets/flask"
    assert data["total_commits"] == 673
    assert len(data["starter_questions"]) > 0

def test_get_hotspots():
    response = client.get("/api/hotspots/flask?top_n=5")
    assert response.status_code == 200
    data = response.json()
    assert data["repo_id"] == "flask"
    assert "hotspots" in data
    assert len(data["hotspots"]) <= 5

def test_get_ownership():
    response = client.get("/api/ownership/flask")
    assert response.status_code == 200
    data = response.json()
    assert data["repo_id"] == "flask"
    assert "ownership" in data
    assert "bus_factor_risk" in data["ownership"]

def test_get_coupling():
    response = client.get("/api/coupling/flask?top_n=5")
    assert response.status_code == 200
    data = response.json()
    assert data["repo_id"] == "flask"
    assert "couplings" in data

def test_get_symbols():
    response = client.get("/api/symbols/flask?top_n=5")
    assert response.status_code == 200
    data = response.json()
    assert data["repo_id"] == "flask"
    assert "symbols" in data

def test_get_leaderboard():
    response = client.get("/api/eval/leaderboard")
    assert response.status_code == 200
    data = response.json()
    assert "leaderboard" in data
