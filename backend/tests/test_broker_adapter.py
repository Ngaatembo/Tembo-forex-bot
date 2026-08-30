import pytest

from app.execution.broker_adapter import PaperBrokerAdapter, get_broker_adapter


def test_default_adapter_is_paper():
    adapter = get_broker_adapter()
    assert isinstance(adapter, PaperBrokerAdapter)


@pytest.mark.asyncio
async def test_paper_adapter_never_touches_real_money():
    adapter = get_broker_adapter()
    account = await adapter.get_account()
    assert account["mode"] == "paper"
