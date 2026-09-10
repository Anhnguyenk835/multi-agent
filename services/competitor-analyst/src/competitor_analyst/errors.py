class CompetitorAnalystError(Exception):
    """Base class for errors raised by the Competitor Analyst's AI-calling code."""


class ProviderConfigurationError(CompetitorAnalystError):
    """A missing/invalid API key, or a request a provider rejected as invalid."""


class ProviderUnavailableError(CompetitorAnalystError):
    """OpenAI failed with a retryable transport or rate-limit error."""


class InvalidOutputError(CompetitorAnalystError):
    """The provider completed, but the agent output was missing or invalid."""
