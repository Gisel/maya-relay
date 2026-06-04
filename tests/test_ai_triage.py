from app.ai_triage import OpenAIMessageTriage, _compact_summary, _extract_response_text
from app.config import Settings


def test_extract_response_text_supports_output_text_helper_shape():
    assert _extract_response_text({"output_text": "Intent: quote request"}) == "Intent: quote request"


def test_extract_response_text_supports_raw_responses_output_shape():
    payload = {
        "output": [
            {
                "content": [
                    {"type": "output_text", "text": "Intent: quote request"},
                    {"type": "output_text", "text": "Missing: dimensions"},
                ]
            }
        ]
    }

    assert _extract_response_text(payload) == "Intent: quote request\nMissing: dimensions"


def test_compact_summary_limits_to_three_content_lines_and_360_characters():
    summary = _compact_summary("\n".join([f"Line {index}" for index in range(1, 8)]))

    assert summary == "Line 1\nLine 2\nLine 3"


def test_compact_summary_adds_separator_before_suggested_reply():
    summary = _compact_summary(
        "Intent: quote request\n"
        "Missing: size and deadline\n"
        "#C0001 Please send size and deadline."
    )

    assert summary == (
        "Intent: quote request\n"
        "Missing: size and deadline\n"
        "---\n"
        "#C0001 Please send size and deadline."
    )


def test_openai_triage_uses_low_reasoning_and_enough_output_tokens(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"output_text": "Intent: quote request"}

    def fake_post(*_args, **kwargs):
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr("app.ai_triage.requests.post", fake_post)
    triage = OpenAIMessageTriage(
        Settings(OPENAI_API_KEY="test-key", OPENAI_MODEL="gpt-5-mini", ENABLE_AI_TRIAGE=True)
    )

    assert (
        triage.summarize(body="Need a banner quote", has_attachments=False, conversation_code="C0001")
        == "Intent: quote request"
    )
    assert captured["json"]["max_output_tokens"] == 300
    assert captured["json"]["reasoning"] == {"effort": "low"}
    assert captured["json"]["text"] == {"verbosity": "low"}
    assert "Conversation reply code: #C0001" in captured["json"]["input"]
