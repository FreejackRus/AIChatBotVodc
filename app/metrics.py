from prometheus_client import Counter, Histogram

HTTP_REQUESTS = Counter(
    "vodc_http_requests_total",
    "HTTP requests by method, route and status.",
    ("method", "route", "status"),
)
HTTP_LATENCY = Histogram(
    "vodc_http_request_duration_seconds",
    "HTTP request latency.",
    ("method", "route"),
)
CHAT_MESSAGES = Counter(
    "vodc_chat_messages_total",
    "Accepted chat inputs.",
    ("input_type",),
)
CHAT_SESSIONS = Counter(
    "vodc_chat_sessions_total",
    "Created chat sessions.",
)
BOOKING_REDIRECTS = Counter(
    "vodc_booking_redirects_total",
    "Validated redirects to the VODC booking form.",
)
CHAT_STREAM_SECONDS = Histogram(
    "vodc_chat_stream_duration_seconds",
    "End-to-end duration of an SSE message stream.",
    ("input_type",),
)
CHAT_ERRORS = Counter(
    "vodc_chat_errors_total",
    "Safe public chat errors.",
    ("code",),
)
DEPENDENCY_READY = Counter(
    "vodc_dependency_readiness_checks_total",
    "Readiness checks by dependency and result.",
    ("dependency", "ready"),
)
MODEL_UPSTREAM_REQUESTS = Counter(
    "vodc_model_upstream_requests_total",
    "Requests sent to a local model replica.",
    ("replica",),
)
MODEL_UPSTREAM_ERRORS = Counter(
    "vodc_model_upstream_errors_total",
    "Errors returned by a local model replica before or during streaming.",
    ("replica", "phase"),
)
MODEL_FAILOVERS = Counter(
    "vodc_model_failovers_total",
    "Model requests retried on another replica before the first token.",
)
MODEL_TTFT = Histogram(
    "vodc_model_time_to_first_token_seconds",
    "Time from an upstream request to its first text token.",
    ("replica",),
    buckets=(0.5, 1, 2, 3, 5, 7.5, 10, 15, 20, 30, 60),
)
