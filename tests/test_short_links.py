from app.short_links import generate_short_token


def test_generate_short_token_default_length():
    assert len(generate_short_token()) == 8


def test_generate_short_token_custom_length():
    assert len(generate_short_token(length=12)) == 12


def test_generate_short_token_excludes_ambiguous_characters():
    token = generate_short_token(length=200)
    assert not set(token) & set("0O1lI")


def test_generate_short_token_is_random():
    tokens = {generate_short_token() for _ in range(50)}
    assert len(tokens) == 50
