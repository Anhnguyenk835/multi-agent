class MarketAgentError(Exception):
    """Base class for every error raised by the market-agent service's own AI-calling code."""


class ProviderConfigurationError(MarketAgentError):
    """A missing/invalid API key, or a request a provider rejected as invalid."""


class ProviderUnavailableError(MarketAgentError):
    """OpenAI failed with a retryable transport or rate-limit error."""


class InvalidOutputError(MarketAgentError):
    """The provider completed, but the agent output was missing or invalid."""
