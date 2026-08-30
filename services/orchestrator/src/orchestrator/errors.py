from distributed_agent_contracts import ContractError, ErrorCode


class AgentCallError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        retryable: bool,
        attempts: int = 1,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.attempts = attempts

    def after_attempt(self, attempt: int) -> "AgentCallError":
        return AgentCallError(
            self.code,
            self.message,
            retryable=self.retryable,
            attempts=attempt,
        )

    def to_contract_error(self) -> ContractError:
        return ContractError(
            code=self.code,
            message=self.message,
            retryable=self.retryable,
        )


class WorkflowConflictError(Exception):
    """Raised when a request ID is reused for a different logical workflow."""
