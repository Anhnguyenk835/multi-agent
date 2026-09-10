import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator

ContractVersion = Literal["v1"]
NonEmptyText = Annotated[str, Field(min_length=1, max_length=10_000)]
# Unlike NonEmptyText, intentionally uncapped.
LongText = Annotated[str, Field(min_length=1)]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ContractStatus(StrEnum):
    SUCCESS = "success"
    DEGRADED = "degraded"
    FAILED = "failed"


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    UPSTREAM_INVALID_RESPONSE = "UPSTREAM_INVALID_RESPONSE"
    RATE_LIMITED = "RATE_LIMITED"
    WORKFLOW_ABORTED = "WORKFLOW_ABORTED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class RequestMetadata(ContractModel):
    contract_version: ContractVersion = "v1"
    request_id: UUID
    trace_id: Annotated[str, Field(min_length=1, max_length=256)]
    attempt: Annotated[int, Field(ge=1)] = 1
    deadline_at: datetime | None = None


def copy_request_metadata(request: RequestMetadata) -> dict[str, object]:
    """Copy only wire metadata fields into a response model constructor."""
    return request.model_dump(include=set(RequestMetadata.model_fields))


class ContractError(ContractModel):
    code: ErrorCode
    message: NonEmptyText
    retryable: bool = False


class ResponseMetadata(RequestMetadata):
    status: ContractStatus
    warnings: list[NonEmptyText] = Field(default_factory=list, max_length=20)
    error: ContractError | None = None

    @model_validator(mode="after")
    def validate_error_status(self) -> "ResponseMetadata":
        if self.status is ContractStatus.FAILED and self.error is None:
            raise ValueError("failed responses require an error")
        if self.status is not ContractStatus.FAILED and self.error is not None:
            raise ValueError("only failed responses may include an error")
        return self


class Source(ContractModel):
    title: NonEmptyText
    url: AnyHttpUrl
    publisher: NonEmptyText
    published_at: datetime | None = None
    retrieved_at: datetime
    # Never forwarded past Analyst — Writer only ever sees `Citation`.
    content: LongText | None = None


class Finding(ContractModel):
    title: NonEmptyText
    claim: NonEmptyText
    source: Source


class CompetitiveSignal(ContractModel):
    topic: NonEmptyText
    observation: NonEmptyText
    source: Source


class Citation(ContractModel):
    """A content-free source reference: enough to link to and label a source,
    without re-exposing the full page text past Analyst."""

    title: NonEmptyText
    url: AnyHttpUrl
    publisher: NonEmptyText


_CITATION_MARKER = re.compile(r"\[(\d+)\]")


def render_citation_links(content: str, citations: list[Citation]) -> str:
    """Turn bare `[N]` markers into markdown links (1-based index into `citations`).

    Out-of-range markers are left as plain text.
    """

    def _replace(match: re.Match[str]) -> str:
        index = int(match.group(1))
        if not 1 <= index <= len(citations):
            return match.group(0)
        citation = citations[index - 1]
        title = _escape_link_title(f"{citation.title} — {citation.publisher}")
        # <...> destination: an unwrapped URL containing "(" or ")" would
        # otherwise be misread as the end of the link.
        return f'[{index}](<{citation.url}> "{title}")'

    return _CITATION_MARKER.sub(_replace, content)


def _escape_link_title(title: str) -> str:
    escaped = title.replace("\\", "\\\\").replace('"', '\\"')
    return " ".join(escaped.split())
