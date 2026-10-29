from radar import text, pain


def test_tokens_keep_non_latin_scripts():
    assert "मंडी" in text.tokens("मंडी भाव आज")
    assert "preço" in text.tokens("O preço do mandi")
    assert text.tokens("作物保险 理赔")  # CJK is bigram-split, never dropped


def test_tokens_ascii_unchanged():
    assert list(text.tokens("Don't hate-this API 2")) == ["don't", "hate", "this", "api", "2"]


def test_content_words_non_ascii():
    assert pain.content_words("मंडी भाव")
