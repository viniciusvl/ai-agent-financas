import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import SECRET_HEADER, WEBHOOK_PATH, build_service, create_app

pytestmark = pytest.mark.task("T08")

SECRET = "s3cr3t-token"


class FakeService:
    def __init__(self):
        self.updates = []

    async def handle_update(self, update):
        self.updates.append(update)


def settings(**kw):
    data = dict(telegram_bot_token="123:ABC", telegram_webhook_secret=SECRET)
    data.update(kw)
    return Settings(_env_file=None, **data)


@pytest.fixture
def service():
    return FakeService()


@pytest.fixture
def client(service):
    with TestClient(create_app(settings(), service=service)) as c:
        yield c


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_webhook_without_secret_is_forbidden(client, service):
    response = client.post(WEBHOOK_PATH, json={"update_id": 1})
    assert response.status_code == 403
    assert service.updates == []


def test_webhook_with_wrong_secret_is_forbidden(client, service):
    response = client.post(WEBHOOK_PATH, json={"update_id": 1}, headers={SECRET_HEADER: "nope"})
    assert response.status_code == 403
    assert service.updates == []


def test_webhook_dispatches_update(client, service):
    update = {"update_id": 10, "message": {"text": "oi"}}
    response = client.post(WEBHOOK_PATH, json=update, headers={SECRET_HEADER: SECRET})
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert service.updates == [update]


def test_webhook_invalid_json(client, service):
    response = client.post(
        WEBHOOK_PATH,
        content=b"not json",
        headers={SECRET_HEADER: SECRET, "content-type": "application/json"},
    )
    assert response.status_code == 400
    assert service.updates == []


def test_duplicate_update_id_is_processed_once(client, service):
    update = {"update_id": 11, "message": {"text": "oi"}}
    for _ in range(3):
        response = client.post(WEBHOOK_PATH, json=update, headers={SECRET_HEADER: SECRET})
        assert response.status_code == 200
    assert service.updates == [update]


def test_create_app_requires_secret():
    with pytest.raises(ValueError):
        create_app(settings(telegram_webhook_secret=""), service=FakeService())


def test_build_service_wires_real_dependencies(monkeypatch, tmp_path):
    import app.sheets as sheets_module
    from app.bot import BotService

    sentinel = object()
    monkeypatch.setattr(
        sheets_module.SheetsRepository,
        "from_service_account",
        classmethod(lambda cls, *a, **k: sentinel),
    )
    service = build_service(
        settings(
            allowed_user_ids="1,2",
            whisper_api_key="w",
            deepseek_api_key="d",
            google_sheet_id="sheet",
            db_path=str(tmp_path / "bot.db"),
        )
    )
    assert isinstance(service, BotService)
    assert (tmp_path / "bot.db").exists()
