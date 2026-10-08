# Развёртывание без GitHub Actions

### О хранении секретов

**GitHub Actions Secrets — не серверные переменные окружения.** Если токен Telegram и API-ключ ClaudeHub добавлены в Settings → Secrets and variables → Actions, это не даёт серверу или нашему чату доступа к их значениям. Секреты доступны только явно настроенным workflow; GitHub не позволяет прочитать их значения обратно.

Для постоянного запуска создайте на сервере закрытый от других пользователей файл `.env` с `TELEGRAM_BOT_TOKEN` и `CLAUDEHUB_API_KEY`. Никогда не коммитьте `.env` и не отправляйте содержимое в чат. Названия секретов должны точно совпадать с названиями в [.env.example](../.env.example). Если секреты созданы для Codespaces, проверьте их доступность отдельно: область Codespaces отличается от Actions.

### Предпочтительный MVP: один контейнер + SQLite

В директории клонированного проекта на сервере с Docker/Compose:

```bash
cp .env.example .env
chmod 600 .env
# Впишите реальные значения ключей в .env на сервере (не в Git).
docker compose -f compose.sqlite.yaml up -d --build
docker compose -f compose.sqlite.yaml ps
```

SQLite хранится в постоянном Docker volume `sushef-data`. Один экземпляр Telegram long polling: не запускайте второго экземпляра с тем же токеном. Обновление: `docker compose -f compose.sqlite.yaml up -d --build`.

### Альтернативный запуск с PostgreSQL

Используйте `compose.yaml` и укажите в `.env` дополнительную переменную `POSTGRES_PASSWORD` — сильный случайный пароль без URL-спецсимволов. Команда: `docker compose up -d --build`.

### Проверка без раскрытия секретов

1. Проверьте `docker compose -f compose.sqlite.yaml ps` — состояние контейнера.
2. В личном чате Telegram: `/start` → «Что приготовить?» → список продуктов.
3. Проверьте рецепт, пошаговую готовку, избранное, профиль и очистку `/reset`.
4. После смены аллергенов убедитесь, что старый рецепт сброшен; проверьте `/privacy` и `/delete_me` на тестовом аккаунте.
5. Smoke-test API делает настоящий запрос и расходует токены. Статус Docker сам по себе не доказывает успешную работу ClaudeHub.

**Политика расходов:** GitHub Actions не создаём и не запускаем ради проверки. Деплой исключительно через локальный доступ к серверу. Существующие сервисы на сервере не трогать.

Источники: [GitHub Secrets](https://docs.github.com/en/actions/concepts/security/secrets), [Docker Compose environment](https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/).
