from sotoki.posts import PostGenerator
from sotoki.utils.shared import context


def test_without_unanswered_skips_post_without_answers_key(monkeypatch):
    monkeypatch.setattr(context, "without_unanswered", True)
    generator = PostGenerator()
    released = []
    monkeypatch.setattr(generator, "release", lambda: released.append(True))

    generator.processor({"Id": "40"})

    assert released == [True]
