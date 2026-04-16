from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_listar_eventos():
    response = client.get("/eventos")
    assert response.status_code == 200


def test_filtrar_porte():
    response = client.get("/eventos/porte/Megaevento")
    assert response.status_code == 200