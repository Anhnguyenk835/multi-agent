class ResearcherError(Exception):
    """Base class for every error raised by the researcher service's own AI-calling code."""


class ProviderConfigurationError(ResearcherError):
    """A missing/invalid API key, or a request a provider rejected as invalid."""


class GroundingError(ResearcherError):
    """The model cited a source_tag that does not match any search result."""


class ToolCallLimitReachedError(ResearcherError):
    """The ReAct loop hit its tool-call limit before producing a structured response."""
