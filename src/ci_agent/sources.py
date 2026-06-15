from __future__ import annotations

from .models import SourceConfig, SourceType


DEFAULT_SOURCES: list[SourceConfig] = [
    SourceConfig(
        name="OpenAI News",
        type=SourceType.RSS,
        url="https://openai.com/news/rss.xml",
    ),
    SourceConfig(
        name="Google DeepMind Blog",
        type=SourceType.RSS,
        url="https://deepmind.google/blog/rss.xml",
    ),
    SourceConfig(
        name="Hugging Face Blog",
        type=SourceType.RSS,
        url="https://huggingface.co/blog/feed.xml",
    ),
    SourceConfig(
        name="NVIDIA AI Blog",
        type=SourceType.RSS,
        url="https://blogs.nvidia.com/blog/category/deep-learning/feed/",
    ),
    SourceConfig(
        name="LangChain Blog",
        type=SourceType.RSS,
        url="https://blog.langchain.com/rss/",
    ),
    SourceConfig(
        name="arXiv cs.AI",
        type=SourceType.RSS,
        url="https://export.arxiv.org/rss/cs.AI",
    ),
]
