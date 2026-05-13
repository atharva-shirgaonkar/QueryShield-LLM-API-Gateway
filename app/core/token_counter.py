"""Token counting helpers."""

import tiktoken


def count_tokens(text: str, model: str) -> int:
    """Count tokens for text with a model-specific tokenizer."""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        return len(text.split())

    return len(encoding.encode(text))
