import pytest

from app.domain.funnel import transition
from app.domain.intents import Intent, classify_intent, policy_for
from app.domain.models import FunnelState, InputType


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Нужно сделать МРТ", Intent.SERVICE_SEARCH),
        ("Хочу выбрать врача-кардиолога", Intent.DOCTOR_SEARCH),
        ("Как подготовиться к УЗИ?", Intent.PREPARATION),
        ("Сколько стоит КТ?", Intent.PRICE),
        ("Есть свободное время завтра?", Intent.AVAILABILITY),
        ("Как записаться на приём?", Intent.BOOKING),
        ("Где находится филиал?", Intent.ORGANIZATIONAL_INFO),
        ("Расскажите подробнее", Intent.UNKNOWN),
    ],
)
def test_intent_catalog(text, expected):
    assert classify_intent(text) is expected


def test_informational_intents_do_not_advance_booking_funnel():
    state = transition(
        FunnelState.DISCOVERY,
        InputType.TEXT,
        intent=Intent.ORGANIZATIONAL_INFO,
    )
    assert state is FunnelState.DISCOVERY
    assert policy_for(Intent.ORGANIZATIONAL_INFO).uses_mis is False


def test_service_intent_advances_to_shortlist():
    state = transition(
        FunnelState.DISCOVERY,
        InputType.TEXT,
        has_services=True,
        intent=Intent.SERVICE_SEARCH,
    )
    assert state is FunnelState.SERVICE_SHORTLIST
