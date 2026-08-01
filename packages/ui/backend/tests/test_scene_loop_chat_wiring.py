"""get_scene_loop wiring: chat_log + ooc_exchanges reach SceneLoop."""

from __future__ import annotations

from typing import Any

from monitor_ui.routers import chat_loops


class _FakeLoop:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.chat_log = kwargs.get("chat_log")


def test_get_scene_loop_passes_and_refreshes_chat_log(monkeypatch) -> None:
    monkeypatch.setattr(chat_loops, "SceneLoop", _FakeLoop)
    chat_loops._SCENE_LOOPS.clear()
    session: dict[str, Any] = {"ooc_exchanges": [{"question": "q", "answer": "a"}]}
    sid = "s1"
    scene_id = "11111111-1111-1111-1111-111111111111"
    story_id = "22222222-2222-2222-2222-222222222222"

    log1 = [{"role": "player", "content": "hi"}]
    loop1 = chat_loops.get_scene_loop(sid, session, scene_id=scene_id, story_id=story_id, chat_log=log1)
    assert loop1.kwargs["chat_log"] is log1
    assert loop1.kwargs["ooc_exchanges"] is session["ooc_exchanges"]

    # Cache hit: same signature, but the chat log reference must refresh.
    log2 = [{"role": "player", "content": "hi"}, {"role": "gm", "content": "yo"}]
    loop2 = chat_loops.get_scene_loop(sid, session, scene_id=scene_id, story_id=story_id, chat_log=log2)
    assert loop2 is loop1
    assert loop2.chat_log is log2