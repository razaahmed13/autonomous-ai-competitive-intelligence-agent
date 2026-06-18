from __future__ import annotations

from .models import SourceConfig, SourceType


DEFAULT_SOURCES: list[SourceConfig] = [
    SourceConfig(
        name="OpenAI Blog",
        type=SourceType.RSS,
        url="https://openai.com/news/rss.xml",
    ),
    SourceConfig(
        name="Anthropic News",
        type=SourceType.RSS,
        url="https://www.anthropic.com/news",
    ),
    SourceConfig(
        name="Google DeepMind Blog",
        type=SourceType.RSS,
        url="https://deepmind.google/blog/rss.xml",
    ),
    SourceConfig(
        name="Meta AI Blog",
        type=SourceType.RSS,
        url="https://ai.meta.com/blog/",
    ),
    SourceConfig(
        name="Microsoft AI Blog",
        type=SourceType.RSS,
        url="https://azure.microsoft.com/en-us/blog/feed/",
    ),
    SourceConfig(
        name="NVIDIA Technical Blog",
        type=SourceType.RSS,
        url="https://developer.nvidia.com/blog/category/generative-ai/feed/",
    ),
    SourceConfig(
        name="Hugging Face Blog",
        type=SourceType.RSS,
        url="https://huggingface.co/blog/feed.xml",
    ),
    SourceConfig(
        name="AWS Machine Learning Blog",
        type=SourceType.RSS,
        url="https://aws.amazon.com/blogs/machine-learning/feed/",
    ),
    SourceConfig(
        name="Mistral AI News",
        type=SourceType.RSS,
        url="https://mistral.ai/rss.xml",
    ),
    SourceConfig(
        name="Cohere Blog",
        type=SourceType.RSS,
        url="https://cohere.com/blog",
    ),
    SourceConfig(
        name="LlamaIndex Blog",
        type=SourceType.RSS,
        url="https://www.llamaindex.ai/blog",
    ),
    SourceConfig(
        name="CrewAI Blog",
        type=SourceType.RSS,
        url="https://blog.crewai.com/rss/",
    ),
    SourceConfig(
        name="Papers with Code",
        type=SourceType.RSS,
        url="https://paperswithcode.com/",
    ),
    SourceConfig(
        name="MIT CSAIL News",
        type=SourceType.RSS,
        url="https://www.csail.mit.edu/rss.xml",
    ),
    SourceConfig(
        name="TechCrunch AI",
        type=SourceType.RSS,
        url="https://techcrunch.com/category/artificial-intelligence/feed/",
    ),
    SourceConfig(
        name="VentureBeat AI",
        type=SourceType.RSS,
        url="https://venturebeat.com/category/ai/feed",
    ),
    SourceConfig(
        name="The Verge AI",
        type=SourceType.RSS,
        url="https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    ),
    SourceConfig(
        name="Ars Technica AI",
        type=SourceType.RSS,
        url="https://arstechnica.com/tag/artificial-intelligence/feed/",
    ),
    SourceConfig(
        name="WIRED AI",
        type=SourceType.RSS,
        url="https://www.wired.com/feed/tag/ai/latest/rss",
    ),
    SourceConfig(
        name="The Decoder",
        type=SourceType.RSS,
        url="https://the-decoder.com/feed/",
    ),
    SourceConfig(
        name="a16z AI",
        type=SourceType.RSS,
        url="https://a16z.com/ai/",
    ),
]
