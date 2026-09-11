"""LLM client error types."""


class MissingAPIKeyError(RuntimeError):
    pass


class LLMOutputParseError(RuntimeError):
    def __init__(self, message: str, raw_output: str, cleaned_output: str, latency_ms: int) -> None:
        super().__init__(message)
        self.raw_output = raw_output
        self.cleaned_output = cleaned_output
        self.latency_ms = latency_ms


class LLMRequestError(RuntimeError):
    def __init__(self, message: str, status_code: int, response_text: str, latency_ms: int) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text
        self.latency_ms = latency_ms
