from ai_platform.demo import answer


def test_citation():
    assert "[source: doc-1]" in answer("What?", {"text": "Example", "source_id": "doc-1"})


def test_abstention():
    assert answer("What?", None) == "Insufficient evidence to answer."
