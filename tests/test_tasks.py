def test_create_and_list_tasks(client):
    response = client.post(
        "/tasks",
        json={"title": "Write tests", "description": "Cover the task API"},
    )

    assert response.status_code == 201
    created = response.json()
    assert created["id"] > 0
    assert created["title"] == "Write tests"
    assert created["description"] == "Cover the task API"
    assert created["completed"] is False
    assert created["created_at"]

    listed = client.get("/tasks")
    assert listed.status_code == 200
    assert created["id"] in [task["id"] for task in listed.json()]


def test_get_task_by_id(client):
    created = client.post(
        "/tasks", json={"title": "Read task", "description": "Details"}
    ).json()

    response = client.get(f"/tasks/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert response.json()["title"] == "Read task"


def test_get_missing_task_returns_404(client):
    response = client.get("/tasks/999999")

    assert response.status_code == 404


def test_put_replaces_task_fields(client):
    created = client.post(
        "/tasks", json={"title": "Draft", "description": "Temporary"}
    ).json()

    response = client.put(
        f"/tasks/{created['id']}",
        json={"title": "Final", "completed": True},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Final"
    assert response.json()["description"] is None
    assert response.json()["completed"] is True


def test_put_requires_title_and_completed(client):
    created = client.post("/tasks", json={"title": "Existing"}).json()

    response = client.put(
        f"/tasks/{created['id']}",
        json={"title": "Incomplete replacement"},
    )

    assert response.status_code == 422


def test_put_missing_task_returns_404(client):
    response = client.put(
        "/tasks/999999",
        json={"title": "Missing", "completed": False},
    )

    assert response.status_code == 404


def test_delete_task_and_missing_task_returns_404(client):
    created = client.post("/tasks", json={"title": "Remove me"}).json()

    deleted = client.delete(f"/tasks/{created['id']}")
    assert deleted.status_code == 204
    assert deleted.content == b""

    missing = client.delete(f"/tasks/{created['id']}")
    assert missing.status_code == 404


def test_task_title_must_not_be_blank(client):
    response = client.post("/tasks", json={"title": "   "})

    assert response.status_code == 422
