# SPDX-License-Identifier: Apache-2.0
import pytest

import convsim_core.runtime  # ensures built-in runtimes are registered
from convsim_core.runtime.fake import FakeChatRuntime
from convsim_core.runtime.registry import build_runtime, list_runtime_ids


def test_fake_runtime_is_registered():
    assert "fake" in list_runtime_ids()


def test_build_runtime_returns_fake_instance():
    rt = build_runtime("fake")
    assert isinstance(rt, FakeChatRuntime)


def test_build_runtime_returns_new_instance_each_call():
    rt1 = build_runtime("fake")
    rt2 = build_runtime("fake")
    assert rt1 is not rt2


def test_build_runtime_unknown_id_raises_key_error():
    with pytest.raises(KeyError, match="unknown-provider"):
        build_runtime("unknown-provider")


def test_build_runtime_error_message_lists_available_runtimes():
    with pytest.raises(KeyError) as exc_info:
        build_runtime("no-such-runtime")
    assert "fake" in str(exc_info.value)


def test_list_runtime_ids_is_sorted():
    ids = list_runtime_ids()
    assert ids == sorted(ids)
