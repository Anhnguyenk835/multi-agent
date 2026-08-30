class AnalystError(Exception):
    """Base class for every error raised by the analyst service's own AI-calling code."""


class ProviderConfigurationError(AnalystError):
    """A missing/invalid API key, or a request OpenAI rejected as invalid."""


class ProviderUnavailableError(AnalystError):
    """OpenAI failed with a retryable error (timeout, rate limit, connection
    error, or a 5xx-equivalent response)."""


class InvalidOutputError(AnalystError):
    """A provider responded successfully but the content was not valid JSON
    or did not validate against the requested schema."""
