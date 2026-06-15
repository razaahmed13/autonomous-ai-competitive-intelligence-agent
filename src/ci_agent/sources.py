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
        name="LangChain Blog",
        type=SourceType.RSS,
        url="https://www.langchain.com/blog/rss.xml",
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
        name="Zapier AI Blog",
        type=SourceType.RSS,
        url="https://zapier.com/blog/feeds/latest/",
    ),
    SourceConfig(
        name="n8n Blog",
        type=SourceType.RSS,
        url="https://blog.n8n.io/rss/",
    ),
    SourceConfig(
        name="arXiv cs.AI",
        type=SourceType.RSS,
        url="https://export.arxiv.org/rss/cs.AI",
    ),
    SourceConfig(
        name="arXiv cs.LG",
        type=SourceType.RSS,
        url="https://export.arxiv.org/rss/cs.LG",
    ),
    SourceConfig(
        name="arXiv cs.CL",
        type=SourceType.RSS,
        url="https://export.arxiv.org/rss/cs.CL",
    ),
    SourceConfig(
        name="Papers with Code",
        type=SourceType.RSS,
        url="https://paperswithcode.com/",
    ),
    SourceConfig(
        name="Berkeley BAIR Blog",
        type=SourceType.RSS,
        url="https://bair.berkeley.edu/blog/feed.xml",
    ),
    SourceConfig(
        name="Stanford HAI Blog",
        type=SourceType.RSS,
        url="https://hai.stanford.edu/news",
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
