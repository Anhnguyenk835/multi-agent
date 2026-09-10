class MarketAnalystError(Exception):
    """Base class for errors raised by the Market Analyst's AI-calling code."""


class ProviderConfigurationError(MarketAnalystError):
    """A missing/invalid API key, or a request a provider rejected as invalid."""


class GroundingError(MarketAnalystError):
    """The model cited a source_tag that does not match any search result."""


class InvalidOutputError(MarketAnalystError):
    """The model completed without a valid structured response."""


class ToolCallLimitReachedError(MarketAnalystError):
    """The ReAct loop hit its tool-call limit before producing a structured response."""
