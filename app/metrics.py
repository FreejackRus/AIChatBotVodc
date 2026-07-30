from prometheus_client import Counter, Gauge, Histogram

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
GUARDRAIL_DECISIONS = Counter(
    "vodc_guardrail_decisions_total",
    "Deterministic guardrail decisions before tools and before SSE output.",
    ("direction", "decision"),
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
RAG_SEARCHES = Counter(
    "vodc_rag_searches_total",
    "Knowledge searches by result.",
    ("result",),
)
RAG_SEARCH_SECONDS = Histogram(
    "vodc_rag_search_duration_seconds",
    "End-to-end knowledge search duration.",
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)
KNOWLEDGE_INGESTION_RUNS = Counter(
    "vodc_knowledge_ingestion_runs_total",
    "Knowledge ingestion runs by result.",
    ("result",),
)
KNOWLEDGE_INGESTION_CHUNKS = Counter(
    "vodc_knowledge_ingestion_chunks_total",
    "Chunks replaced by successful ingestion runs.",
)
CATALOG_AUDIT_RUNS = Counter(
    "vodc_catalog_audit_runs_total",
    "Public service catalogue audit runs by result.",
    ("result",),
)
CATALOG_AUDIT_SERVICES = Gauge(
    "vodc_catalog_audit_services",
    "Unique service codes in the latest completed catalogue audit.",
)
CATALOG_AUDIT_ISSUES = Gauge(
    "vodc_catalog_audit_issues",
    "Issues in the latest completed catalogue audit.",
)
SOURCE_STAGING_RUNS = Counter(
    "vodc_source_staging_runs_total",
    "Semantic source staging runs by result.",
    ("result",),
)
SOURCE_STAGING_CREATED = Gauge(
    "vodc_source_staging_created",
    "New semantic source versions in the latest staging run.",
)
SOURCE_STAGING_QUARANTINED = Gauge(
    "vodc_source_staging_quarantined",
    "Quarantined semantic source versions in the latest staging run.",
)
