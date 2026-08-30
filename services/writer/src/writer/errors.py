class WriterError(Exception):
    """Base class for every error raised by the writer service's own AI-calling code."""


class ProviderConfigurationError(WriterError):
    """A missing/invalid API key, or a request OpenAI rejected as invalid."""


class ProviderUnavailableError(WriterError):
    """OpenAI failed with a retryable error (timeout, rate limit, connection
    error, or a 5xx-equivalent response)."""


class InvalidOutputError(WriterError):
    """A provider responded successfully but the content was not valid JSON
    or did not validate against the requested schema."""
