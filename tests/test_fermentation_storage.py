from decimal import Decimal

import pytest

from sushef.storage import Storage


@pytest.fixture
async def db(tmp_path):
    storage = Storage("sqlite+aiosqlite:///" + str(tmp_path / "fermentation.db"))
    await storage.create_tables()
    yield storage
    await storage.close()


@pytest.mark.asyncio
async def test_private_batches_readings_and_deletion(db):
    owner, intruder = 91827, 91828
    batch_id = await db.create_fermentation_batch(owner, "vegetables", "Капуста на пробу")
    assert not await db.fermentation_batch(intruder, batch_id)
    assert not await db.log_fermentation(intruder, batch_id, "22", "4.2", "попытка")
    assert await db.log_fermentation(owner, batch_id, "22", "4.2", "пузырьки")
    batch = await db.fermentation_batch(owner, batch_id)
    assert batch["readings"][0]["ph"] == "4.2"
    assert not await db.finish_fermentation_batch(intruder, batch_id)
    assert await db.finish_fermentation_batch(owner, batch_id)
    assert not await db.log_fermentation(owner, batch_id, "22", None, "закрыто")
    assert not await db.delete_fermentation_batch(intruder, batch_id)
    assert await db.delete_fermentation_batch(owner, batch_id)
    assert await db.fermentation_batch(owner, batch_id) is None


@pytest.mark.asyncio
async def test_delete_me_removes_microbiology_journal(db):
    owner = 41152
    batch_id = await db.create_fermentation_batch(owner, "koji", "Рис, только заметки")
    await db.log_fermentation(owner, batch_id, None, None, "Наблюдение")
    await db.delete_user(owner)
    assert await db.list_fermentation_batches(owner) == []
    assert await db.fermentation_batch(owner, batch_id) is None


@pytest.mark.asyncio
async def test_invalid_batch_data_rejected(db):
    with pytest.raises(ValueError):
        await db.create_fermentation_batch(1, "unknown", "Опыт")
    with pytest.raises(ValueError):
        await db.create_fermentation_batch(1, "vegetables", "")
