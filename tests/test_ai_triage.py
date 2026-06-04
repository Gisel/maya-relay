from app.ai_triage import _compact_summary, _extract_response_text


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


def test_compact_summary_limits_to_four_lines_and_500_characters():
    summary = _compact_summary("\n".join([f"Line {index}" for index in range(1, 8)]))

    assert summary == "Line 1\nLine 2\nLine 3\nLine 4"
