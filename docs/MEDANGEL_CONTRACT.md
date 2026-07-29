# Контракт адаптера «МедАнгел»

Репозиторий реализует anti-corruption layer, но фактические URL и поля должны
быть сопоставлены с Swagger/OpenAPI тестового стенда.

## Внутренние модели

- `Service`: `id`, `title`, `description`, `price`, `branch_id`, `updated_at`.
- `Doctor`: `id`, `title`, `specialty`, `branch_id`, `service_id`.
- `Slot`: `id`, `starts_at` ISO 8601 с часовым поясом, `doctor_id`,
  `service_id`, `branch_id`.

Настраиваемые endpoints:

- `MEDANGEL_SERVICES_PATH`;
- `MEDANGEL_DOCTORS_PATH`;
- `MEDANGEL_SLOTS_PATH`.

Адаптер принимает коллекцию непосредственно либо в поле `items`/`data`.
Идентификаторы должны быть стабильными строками. Перед пилотом необходимо
заменить этот общий mapping на точные DTO контракта и добавить contract tests
по обезличенным ответам стенда.

## Обязательные сценарии стенда

1. Поиск и повторная проверка услуги.
2. Врачи, отфильтрованные по услуге и филиалу.
3. Слоты с часовым поясом Europe/Moscow.
4. Исчезнувшая услуга, врач или занятый слот.
5. Timeout, 401/403, 429, 5xx, пустой и повреждённый JSON.
6. Стабильность ID между справочником и расписанием.

Чат не вызывает create/update/cancel appointment. `booking-link` лишь
повторно валидирует слот и создаёт URL штатной формы VODC.
