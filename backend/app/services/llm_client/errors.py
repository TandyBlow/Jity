"""LLM client error types."""

from openai import APIConnectionError, APITimeoutError


def request_error_message(exc: Exception) -> str:
    """Give actionable advice without mistaking transport errors for auth failures."""
    status = getattr(exc, "status_code", 0)
    if isinstance(exc, APITimeoutError):
        advice = "LLM 请求超时，请稍后重试；若持续发生，请检查网络、代理及 API 服务状态。"
    elif isinstance(exc, APIConnectionError):
        advice = "无法连接 LLM 服务，请重试；若持续发生，请检查网络、代理、TLS 证书及 LLM_BASE_URL。"
    elif status == 401:
        advice = "LLM 身份验证失败，请检查 API Key。"
    elif status == 402:
        advice = "LLM 账户余额不足，请检查余额。"
    elif status == 403:
        advice = "LLM 请求被拒绝，请检查账户或模型访问权限。"
    elif status == 429:
        advice = "LLM 请求受限，请稍后重试并检查服务商的速率或配额限制。"
    elif status and status >= 500:
        advice = "LLM 服务暂时异常，请稍后重试。"
    else:
        advice = "LLM 请求失败，请检查请求参数和 API 服务返回的错误。"
    return f"{advice} 原始错误: {exc}"


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
