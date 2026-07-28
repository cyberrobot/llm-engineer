import re

import pysbd

from assistant.domain.models import Sentence

segmenter = pysbd.Segmenter(language="en", clean=False)


def split_sentences(text: str) -> list[Sentence]:
    normalized_text = re.sub(r"\s+", " ", text).strip()
    if not normalized_text:
        return []

    sentences = [
        sentence.strip() for sentence in segmenter.segment(normalized_text) if sentence.strip()
    ]

    return [
        Sentence(text=sentence, index=index) for index, sentence in enumerate(sentences, start=1)
    ]
