import re
from datetime import date
from decimal import Decimal

import pytest

from app.domain import Expense
from app.pending_store import PendingExpense, PendingStore

pytestmark = pytest.mark.task("T05")


class Clock:
    def __init__(self, now=1_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


def expense():
    return Expense(amount=Decimal("10"), description="água", spent_at=date(2026, 10, 8))


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def store(tmp_path, clock):
    s = PendingStore(str(tmp_path / "nested" / "bot.db"), ttl_seconds=100, clock=clock)
    s.init()
    return s


def test_init_creates_parent_directory(tmp_path, clock):
    path = tmp_path / "a" / "b" / "bot.db"
    PendingStore(str(path), clock=clock).init()
    assert path.exists()


def test_init_is_idempotent(store):
    store.init()
    store.init()


def test_save_and_get(store, clock):
    pending_id = store.save(chat_id=111, user_id=222, expense=expense())
    assert re.fullmatch(r"[0-9a-f]{12}", pending_id)
    item = store.get(pending_id)
    assert isinstance(item, PendingExpense)
    assert item.id == pending_id
    assert item.chat_id == 111
    assert item.user_id == 222
    assert item.expense == expense()
    assert item.created_at == clock.now


def test_ids_are_unique(store):
    ids = {store.save(1, 1, expense()) for _ in range(50)}
    assert len(ids) == 50


def test_get_unknown_returns_none(store):
    assert store.get("doesnotexist") is None


def test_delete(store):
    pending_id = store.save(1, 1, expense())
    assert store.delete(pending_id) is True
    assert store.delete(pending_id) is False
    assert store.get(pending_id) is None


def test_expired_items_are_not_returned(store, clock):
    pending_id = store.save(1, 1, expense())
    clock.now += 100
    assert store.get(pending_id) is not None
    clock.now += 1
    assert store.get(pending_id) is None


def test_purge_expired(store, clock):
    old = store.save(1, 1, expense())
    clock.now += 50
    fresh = store.save(1, 1, expense())
    clock.now += 60
    assert store.purge_expired() == 1
    assert store.get(old) is None
    assert store.get(fresh) is not None


def test_data_persists_across_instances(tmp_path, clock):
    path = str(tmp_path / "bot.db")
    first = PendingStore(path, clock=clock)
    first.init()
    pending_id = first.save(5, 6, expense())
    second = PendingStore(path, clock=clock)
    second.init()
    assert second.get(pending_id).expense == expense()
