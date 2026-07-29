# Статус интеграционных испытаний

Автоматически проверяется локально:

- новый FastAPI/SSE API;
- state machine и подписанные карточки;
- архитектурные границы и портовые ошибки;
- emergency/refusal/prompt-injection policy;
- очистка ПДн;
- MIS fallback;
- протокол model benchmark и контрольный набор из 20 сценариев;
- отсутствие legacy `/chat`.

Испытания с реальными vLLM, PostgreSQL/pgvector, Redis и стендом
«МедАнгел» выполняются по `docs/ACCEPTANCE_GAPS.md`; до предоставления
внешней инфраструктуры их нельзя отмечать пройденными.
