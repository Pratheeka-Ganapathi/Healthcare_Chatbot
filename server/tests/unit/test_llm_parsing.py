from __future__ import annotations

import pytest

from clinic_bot.adapters.llm.litellm_client import parse_label
from clinic_bot.domain.errors import Unavailable


def test_parses_a_complete_reply() -> None:
    assert parse_label('{"label": "NONE", "reason": "booking"}') == ("NONE", "booking")


def test_reply_cut_off_at_the_token_limit_still_gives_the_label() -> None:
    cut = '{\n  "label": "EMERGENCY",\n  "reason": "The patient reports that their mother colla'
    assert parse_label(cut) == ("EMERGENCY", "")


def test_reply_without_a_label_is_unavailable() -> None:
    with pytest.raises(Unavailable):
        parse_label('{"reas')
