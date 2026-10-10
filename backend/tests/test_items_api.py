from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_item_crud(client: TestClient) -> None:
    created = client.post("/api/items", json={"name": "Widget", "description": "A widget"})
    assert created.status_code == 201
    item_id = created.json()["id"]

    assert client.get(f"/api/items/{item_id}").json()["name"] == "Widget"

    page = client.get("/api/items").json()
    assert page["total"] == 1 and page["items"][0]["id"] == item_id

    updated = client.patch(f"/api/items/{item_id}", json={"description": "Changed"})
    assert updated.status_code == 200 and updated.json()["description"] == "Changed"

    assert client.delete(f"/api/items/{item_id}").status_code == 204
    assert client.get(f"/api/items/{item_id}").status_code == 404


def test_duplicate_name_conflicts(client: TestClient) -> None:
    assert client.post("/api/items", json={"name": "Twin"}).status_code == 201
    response = client.post("/api/items", json={"name": "Twin"})
    assert response.status_code == 409


def test_validation_error(client: TestClient) -> None:
    assert client.post("/api/items", json={"name": ""}).status_code == 422
