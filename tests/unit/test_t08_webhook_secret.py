"""Testes unitários de robustez do segredo do webhook (T08).

A revisão da T08 pediu comparação em bytes do header do segredo: um header
com caractere não-ASCII controlado pelo chamador deve resultar em 403 (e não
em 500 por ``TypeError`` de ``secrets.compare_digest`` com ``str``).
"""

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import SECRET_HEADER, WEBHOOK_PATH, create_app

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


def test_non_ascii_secret_header_is_forbidden_not_500():
    service = FakeService()
    with TestClient(create_app(settings(), service=service)) as client:
        # Enviar os bytes crus do header: o httpx não aceita ``str`` não-ASCII,
        # mas na rede o header chega exatamente assim (codificado em utf-8).
        response = client.post(
            WEBHOOK_PATH,
            json={"update_id": 1},
            headers={SECRET_HEADER: "çãõ".encode()},
        )
    assert response.status_code == 403
    assert service.updates == []
