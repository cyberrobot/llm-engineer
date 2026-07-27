from api.models.evaluation import Sentence
from api.services.split_sentences import split_sentences


def test_split_sentences_returns_numbered_sentences_for_common_punctuation():
    result = split_sentences("Hello world. Are you ready? Go!")

    assert result == [
        Sentence(text="Hello world.", index=1),
        Sentence(text="Are you ready?", index=2),
        Sentence(text="Go!", index=3),
    ]


def test_split_sentences_normalizes_whitespace():
    result = split_sentences("  First sentence.\n\nSecond\t sentence.  ")

    assert result == [
        Sentence(text="First sentence.", index=1),
        Sentence(text="Second sentence.", index=2),
    ]


def test_split_sentences_returns_empty_list_for_blank_text():
    assert split_sentences("") == []
    assert split_sentences(" \n\t ") == []


def test_split_sentences_keeps_trailing_fragment():
    result = split_sentences("Complete sentence. trailing fragment")

    assert result == [
        Sentence(text="Complete sentence.", index=1),
        Sentence(text="trailing fragment", index=2),
    ]


def test_split_sentences_keeps_ellipsis_and_repeated_punctuation_together():
    result = split_sentences("Wait... What?! Really!!")

    assert result == [
        Sentence(text="Wait...", index=1),
        Sentence(text="What?!", index=2),
        Sentence(text="Really!!", index=3),
    ]


def test_split_sentences_keeps_closing_quotes_with_sentence():
    result = split_sentences('She said, "Stop." Then she left.')

    assert result == [
        Sentence(text='She said, "Stop."', index=1),
        Sentence(text="Then she left.", index=2),
    ]


def test_split_sentences_does_not_split_common_abbreviations():
    result = split_sentences("Dr. Smith met Prof. Jones. They talked.")

    assert result == [
        Sentence(text="Dr. Smith met Prof. Jones.", index=1),
        Sentence(text="They talked.", index=2),
    ]


def test_split_sentences_does_not_split_decimal_numbers():
    result = split_sentences("Pi is about 3.14. That is enough.")

    assert result == [
        Sentence(text="Pi is about 3.14.", index=1),
        Sentence(text="That is enough.", index=2),
    ]


def test_split_sentences_handles_acronyms_inside_sentences():
    result = split_sentences("The U.S. economy grew. The U.S. It is complex.")

    assert result == [
        Sentence(text="The U.S. economy grew.", index=1),
        Sentence(text="The U.S.", index=2),
        Sentence(text="It is complex.", index=3),
    ]


def test_split_sentences_handles_no_terminal_punctuation():
    result = split_sentences("A sentence without punctuation")

    assert result == [Sentence(text="A sentence without punctuation", index=1)]
