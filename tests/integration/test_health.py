"""Integration tests for the /health endpoint."""


async def test_health_check_returns_200_when_db_is_up(client):
    """The /health endpoint should return 200 with db=ok when the database is reachable."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["db"] == "ok"