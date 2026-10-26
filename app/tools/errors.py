"""Errors that tools return to the agent or the API: a stable code plus a plain-language message."""

HTTP_STATUS = {
    "VALIDATION_ERROR": 400,
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
    "SLOT_TAKEN": 409,
    "DUPLICATE": 409,
    "ALREADY_CHECKED_IN": 409,
    "ALREADY_ON_LIST": 409,
    "SLOTS_AVAILABLE": 409,
    "INVALID_STATE": 409,
    "QUEUE_FULL": 409,
    "CONFIRMATION_REQUIRED": 422,
    "POLICY_WINDOW": 422,
    "UNSAFE_QUERY": 422,
    "UNAUTHORIZED": 401,
    "INVALID_CREDENTIALS": 401,
    "ACCOUNT_DISABLED": 403,
    "PASSWORD_CHANGE_REQUIRED": 403,
    "USERNAME_TAKEN": 409,
    "RATE_LIMITED": 429,
    "LLM_UNAVAILABLE": 503,
    "DELIVERY_FAILED": 502,
}


class ToolError(Exception):
    def __init__(self, code: str, message: str, **details):
        if code not in HTTP_STATUS:
            raise ValueError(f"unknown error code {code}")
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    @property
    def http_status(self) -> int:
        return HTTP_STATUS[self.code]

    def to_dict(self) -> dict:
        body = {"code": self.code, "message": self.message}
        if self.details:
            body["details"] = self.details
        return body
