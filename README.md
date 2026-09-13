# Mail Receipt Expense Tracker

**License:** [Private, non-commercial use only](LICENSE). Other uses require the copyright holder's written permission.

**[English](#english)** · [Русский](#русский)

<a id="english"></a>
## English

Reads receipt e-mails from an IMAP mailbox, breaks purchases down by store and category, and shows charts.
It started with one Lithuanian grocery chain (Maxima) and now handles any number of stores — Wolt, Domino's,
Topocentras, utility bills — any sender whose e-mail or attached PDF contains an amount. Everything is configured
in the web UI; no config files or SSH needed after the first start.

> **Languages:** the web UI is available in Russian, English and Lithuanian — switch with the RU / EN / LT selector in the
> page header (remembered per browser). Category names and status/health messages are translated; item names of
> Maxima receipts are translated Lithuanian → Russian, so in EN/LT the original Lithuanian item names are shown
> (Russian in the tooltip). Free-form error texts and journal entries written before this feature stay in Russian.

### How it works

1. Once a day (08:00, configurable) the app fetches mails of all enabled stores for a sliding window
   (30 days; widens automatically after downtime). Gmail: the "All Mail" folder is located by its IMAP
   `\All` attribute, so archived mails are seen too.
2. Text is taken from the body (plain or HTML; HTML disguised as plain text is detected) **and from every
   PDF attachment** (pypdf).
3. Parsing depends on the store's *parser* setting. `auto` tries, in this order: the Maxima format, the Wolt/order.site PDF format, Claude (if an API key is set), and finally a generic search for the receipt total:
   - **Maxima** — line items of the receipt, categories from a Lithuanian grocery dictionary, item names
     translated to Russian, reconciled against the receipt total to the cent;
   - **Wolt / order.site** (Sushi Lovers and other restaurants on the Wolt platform) — line items from the
     PDF receipt, total from "Total in EUR / Viso EUR";
   - **generic** — only the total of the mail, found by keywords (Iš viso, Bendra suma, Mokėtina suma, Total,
     Amount due…) — Domino's, Topocentras, Penki, eSIM…; a store set to `generic` never goes to Claude;
   - **Claude** (if an API key is set) — any format, itemised, plus proper translation of item names.
   A store can have a *default category for all purchases* (food delivery → "restaurants & delivery");
   leave it empty to categorise each line item.
4. One order usually arrives as several mails (confirmation, "ready for pickup", PDF invoice): they are merged
   by order/invoice number and the record with the most detailed parse wins. Order keys use an immutable store ID,
   so renaming a store preserves deduplication. Equal amounts alone never merge separate purchases.
   Promotional subjects (nuolaida, pasiūlymai, %…)
   are skipped unless the mail carries a PDF — bodies often contain "example" amounts. Mails are deduplicated
   by `Message-ID`. Cancellations, refunds, failed payments and payment reminders are not expenses.
   A receipt-like mail in which neither a total nor line items could be found is marked `unparsed`; a mail whose
   parsing crashed is kept and retried on the next syncs from the saved text, and after `MAX_FAILED_ATTEMPTS`
   tries (3 by default) it is marked `failed`. Unreadable PDFs, including PDFs without extractable text, are
   marked `unparsed` with the extraction error. Both kinds appear in `/api/health` and under *Problem receipts*.

### Web settings

`/settings` — after setting the initial `ADMIN_TOKEN` locally, other settings can be edited here; saved values take precedence over `.env`,
and the schedule is applied immediately:

- **Mail**: server, mailbox, password (Gmail: app password), folder, timeout; *Test connection* uses the values
  currently typed into the form and shows the folder and the number of mails per store. Sections Mail, Schedule,
  Claude and Access are saved together with the single **Save settings** («Сохранить настройки») button;
  each store row has its own *Save*.
- **Stores**: name, senders (full addresses or domains: `wolt.com, order.site`), parser, default category, on/off.
  *Find in mailbox* scans the mailbox and proposes senders whose mails look like receipts or carry PDFs, with a
  suggested category; *Add* prefills a row. After adding a store run *Synchronise for a year* to backfill its
  history (no full rebuild needed).
- **Schedule and reliability**: time, retries, timeouts, alert thresholds, fetch window. Empty daily time selects interval mode.
- **Claude**: key and model (optional).
- **Access**: all API routes except `/api/live` require `X-Admin-Token`; both pages ask for it.
  Missing tokens or unreadable secrets close access. New tokens need at least 32 printable ASCII characters without spaces.
  Changing the IMAP server, port or mailbox requires entering its password again, including for *Test connection*.
  Connection tests are limited to 5 per 10 minutes; manual sync to 5 per minute.
- **Maintenance**: *Synchronise* (fetch mail now); *Rebuild from mail* («Пересобрать всё из почты», API `POST /api/reprocess`) —
  downloads the history of *enabled* stores and replaces their parsed expenses in one transaction after a successful parse.
  A backup is taken first. Missing previously processed messages block rebuilding; `force=yes` permits an intentional
  reduction of history, but never overrides fetch errors, parse errors or unreadable receipts. Failure or timeout rolls
  back the replacement. Settings/store changes return HTTP 409 while a sync is running.

Secrets live in `data/secrets.json` (0600), other settings in the `settings` table of the database;
`.env` provides initial values only.
Clearing a mail password or Claude key disables its environment fallback; `__reset__` restores it.
The admin token cannot be cleared; resetting it requires a valid token in the environment.
IMAP verifies server certificates and hostnames using the system trust store.

### Run

```bash
cp .env.example .env            # first installation only; preserve an existing .env
chmod 600 .env
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'  # put this value into ADMIN_TOKEN in .env
mkdir -p data
sudo chown -R 10001:10001 data   # non-root container UID/GID on Linux
sudo chmod 700 data
docker compose up -d --build    # http://<host>  (ports 80 and 8080)
```

Data — the `./data` volume: `expenses.db`, `secrets.json`, `backup/` (daily copies for 14 days; copies before a rebuild).
Full walkthrough for a fresh server: [docs/DEPLOY.md](docs/DEPLOY.md).
HTTP and published ports are unchanged. [Security changes and upgrade notes](docs/SECURITY-FIXES-2026-09-13.md).

### Reliability of the daily collection

| Layer | What |
|---|---|
| Scheduler | daily at `SYNC_DAILY_AT`; catch-up sync 30 s after start — with the same retries; on error, retry every 30 min (up to 16 times); a busy lock (manual sync) is waited for, not skipped |
| Hangs | IMAP socket timeout; every sync/rebuild runs in a supervised process that is killed and reaped on the whole-sync timeout |
| Errors | a dropped connection = `error` with retries; one broken mail does not spoil the batch; a mail that failed to parse is retried from the database without IMAP, after N failures — `failed` (visible) |
| Data | `Message-ID` + receipt fingerprint for mails without one; the window widens after downtime; an empty database — maximum window |
| Visibility | `/api/health` → **503** and `problems`: no sync > 26 h, sync error, folder not found, unparsed receipts, no new receipts > 21 days, no enabled stores |
| Backups | after successful syncs and before rebuilds; a rebuild commits all enabled-store changes together, otherwise the old data remains |
| Container / host | `restart: always`, public `/api/live` liveness check, log rotation, non-root user and resource limits |

### API

| Method | Path | What |
|---|---|---|
| GET | `/api/health` | `ok`, `problems`, schedule, state of the last sync; HTTP 503 when there are problems |
| GET | `/api/runs?limit=30` | sync journal |
| GET | `/api/stats?from=&to=&store=` | for a period: total, receipts, average receipt, per day, by store/category/day/month (`days=N`, or no params — all time) |
| GET | `/api/expenses?from=&to=&store=` | expense records |
| GET | `/api/stores` | stores |
| POST | `/api/sync?days=30` | fetch mail now |
| GET/PUT | `/api/settings` * | settings (secrets: presence only; empty = keep, `__clear__` = disable, `__reset__` = restore `.env`) |
| POST | `/api/settings/test-imap` * | connection test (works with unsaved values too) |
| POST/PUT/DELETE | `/api/stores[/{id}]` * | stores (only a store without parsed mails can be deleted — otherwise disable it) |
| POST | `/api/discover?days=90` * | mailbox scan: store candidates |
| GET | `/api/receipts/problems?days=30` * | unparsed / deferred receipts with text |
| POST | `/api/reprocess?confirm=yes[&force=yes][&days=N]` * | rebuild: re-fetch mail and re-parse all *enabled* stores (disabled stores are left untouched) |

All listed routes require `X-Admin-Token`, including rows without the historical `*` marker.
`GET /api/live` is the only public API and returns only `{"ok":true}`.

### Languages / i18n

Dictionaries live in `static/i18n.js` (`I18N.ru/en/lt`, one key set, checked for parity). Static markup uses
`data-i18n` / `data-i18n-ph` / `data-i18n-title`; dynamic strings go through `t(key, params)`. Categories are stored in
Russian and mapped for display with `catName()` / back with `catKey()` when saving a store. The backend returns
`problems_i18n` (codes + params) in `/api/health` and structured `details` in `/api/runs` and `/api/sync`, from which
the UI builds localized messages. To add a language: add a dictionary and a `CATS_I18N` column, a locale in `LOCALES`,
an option to the two `langSel` selects.

### Documentation

- [docs/DEPLOY.md](docs/DEPLOY.md) — deploying on a fresh Linux server
- [docs/DEVNOTES.md](docs/DEVNOTES.md) — developer notes: modules, sync flow, settings, testing, known limits
- [docs/REVIEW-2026-09-12.md](docs/REVIEW-2026-09-12.md) — review findings, fixes, remaining risks and migration notes
- [docs/TESTING.md](docs/TESTING.md) — isolated regression tests and verification commands

### Development

Tests (Python 3.12+ and Node.js):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-dev.lock
.venv/bin/python -m unittest discover -s tests -t . -v -b
node tests/test_ui.cjs
```

Tests use temporary databases and artificial mail; no real IMAP or Claude credentials are needed.

---

<a id="русский"></a>
## Русский

Читает письма-чеки из почтового ящика (IMAP), раскладывает покупки по магазинам и категориям, показывает графики.
Интерфейс — на русском, английском и литовском (переключатель RU / EN / LT в шапке страницы).
Начиналось с Maxima, теперь магазинов сколько угодно: Wolt, Dominos, Topocentras, счета за связь — любой отправитель,
у которого в письме или во вложенном PDF есть сумма. Всё настраивается в веб-интерфейсе.

### Как это работает

1. Раз в день (08:00, настраивается) забираются письма всех включённых магазинов за окно (30 дней, расширяется само после простоя).
   Gmail: папка «Вся почта» находится по IMAP-атрибуту `\All` — архивированные письма тоже видны.
2. Из письма берётся текст (plain/HTML, HTML под видом plain распознаётся) **и текст всех PDF-вложений** (pypdf).
3. Разбор — по настройке магазина; `auto` пробует по порядку: формат Maxima, PDF-чек Wolt/order.site, Claude (если задан ключ), общий поиск итога:
   - **Maxima** — позиции чека, категории по словарю литовских товаров, перевод названий на русский, сверка с итогом до цента;
   - **Wolt / order.site** (Sushi Lovers и другие рестораны на платформе Wolt) — позиции из PDF-чека, итог из «Total in EUR / Viso EUR»;
   - **generic** — только итог письма по ключевым словам (Iš viso, Bendra suma, Mokėtina suma, Total, Amount due…) — Dominos, Topocentras, Penki, eSIM…; магазин с парсером `generic` в Claude не уходит;
   - **Claude** (если задан ключ) — любой формат по позициям, плюс нормальный перевод названий.
   Магазину можно задать «категорию для всех покупок» (доставка еды → «рестораны и доставка»); пусто — категория по каждой позиции.
4. Один заказ часто приходит несколькими письмами (подтверждение, «готов к выдаче», PDF-счёт): они склеиваются по номеру заказа/счёта, остаётся запись с самым подробным разбором. Ключ заказа содержит неизменяемый ID магазина, поэтому переименование не создаёт дублей. Совпадение суммы само по себе не склеивает покупки. Рекламные темы (nuolaida, pasiūlymai, %…) не разбираются, если к письму не приложен PDF. Ключ дедупликации писем — `Message-ID`. Отмены и возвраты проверяются до всех парсеров.
   Нечитаемый PDF, включая документ без извлекаемого текста, помечается `unparsed` с описанием ошибки. Письмо с исключением при разборе повторяется из сохранённого текста и после N неудач откладывается (`failed`). Проблемы видны в health и в настройках.

### Настройки (веб)

`/settings` — после первоначальной установки `ADMIN_TOKEN` на сервере остальные настройки доступны в интерфейсе; значения здесь имеют приоритет над `.env`, расписание применяется сразу:

- **Почта**: сервер, пользователь, пароль (Gmail — пароль приложения), папка, таймаут; кнопка «Проверить подключение» показывает папку и число писем по магазинам.
- **Магазины**: имя, отправители (полные адреса или домены: `wolt.com, order.site`), способ разбора, категория для всех покупок, вкл/выкл.
  «Найти в почте» сканирует ящик и предлагает отправителей с чеко-подобными темами или PDF — с подсказкой категории; «Добавить» заполняет строку.
  После добавления магазина — «Синхронизировать за год», чтобы подтянуть его старые письма (пересборка всей базы для этого не нужна).
- **Расписание и надёжность**: время, повторы, таймауты, пороги тревог, окно выборки. Пустое время ежедневного запуска включает интервальный режим.
- **Claude**: ключ и модель (необязательно).
- **Доступ**: все API, кроме `/api/live`, требуют `X-Admin-Token`; токен запрашивается на обеих страницах. Без токена или при повреждении секретов доступ закрыт. Новый токен должен содержать минимум 32 печатных ASCII-символа без пробелов. При смене IMAP-сервера, порта или пользователя пароль вводится заново, в том числе для проверки подключения. Лимиты: 5 проверок IMAP за 10 минут, 5 ручных синхронизаций в минуту.
- **Обслуживание**: пересборка (`POST /api/reprocess`) сначала скачивает историю *включённых* магазинов, затем заменяет расходы одной транзакцией после успешного разбора. Перед заменой делается копия базы. Пропавшие из выборки обработанные письма блокируют пересборку; `force=yes` разрешает намеренно сократить историю, но не обходит ошибки загрузки, разбора и нечитаемые чеки. При ошибке или таймауте прежние расходы остаются. Во время синка изменение настроек и магазинов возвращает HTTP 409.

Секреты хранятся в `data/secrets.json` (0600), остальные настройки — в таблице `settings` базы; `.env` остаётся начальными значениями.
Очистка пароля почты или ключа Claude отключает и значение из `.env`; `__reset__` возвращает использование окружения. Административный токен очистить нельзя; сброс разрешён только при действительном токене в окружении.
IMAP проверяет сертификат и имя сервера через системное хранилище доверенных сертификатов.

### Запуск

```bash
cp .env.example .env            # только первая установка; существующий .env сохранить
chmod 600 .env
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'  # записать результат в ADMIN_TOKEN файла .env
mkdir -p data
sudo chown -R 10001:10001 data   # необходимо на Linux для контейнера без root
sudo chmod 700 data
docker compose up -d --build    # http://<host>  (ports 80 and 8080)
```

Данные — том `./data`: `expenses.db`, `secrets.json`, `backup/` (ежедневные копии, 14 дней; копии перед пересборкой).
HTTP и опубликованные порты сохранены. [Исправления безопасности и переход на новую версию](docs/SECURITY-FIXES-2026-09-13.md).

### Надёжность ежедневного сбора

| Слой | Что |
|---|---|
| Планировщик | ежедневно в `SYNC_DAILY_AT`; догоняющий синк через 30 с после старта — с теми же повторами; при ошибке повтор каждые 30 мин (до 16 раз); занятый lock (ручной синк) — ждём, не пропускаем день |
| Зависания | таймаут IMAP-сокета; каждый синк/пересборка работает в отдельном процессе, который завершается по общему таймауту с освобождением блокировки |
| Ошибки | обрыв соединения = `error` с повторами; битое письмо не валит батч; письмо с ошибкой разбора повторяется из БД без IMAP, после N неудач — `failed` (видно) |
| Данные | `Message-ID` + отпечаток чека для писем без него; окно расширяется после простоя; пустая база — максимальное окно |
| Видимость | `/api/health` → **503** и `problems`: нет сбора > 26 ч, ошибка синка, папка не найдена, не разобранные чеки, нет новых чеков > 21 дня, нет включённых магазинов |
| Бэкапы | после успешных синков и перед `reprocess`; пересборка фиксируется целиком, иначе сохраняет прежние данные |
| Контейнер / хост | `restart: always`, healthcheck, ротация логов; опциональная cron-страховка на хосте в 08:20 |

### API

| Метод | Путь | Что |
|---|---|---|
| GET | `/api/health` | `ok`, `problems`, расписание, состояние последнего синка; HTTP 503 при проблемах |
| GET | `/api/runs?limit=30` | журнал синхронизаций |
| GET | `/api/stats?from=&to=&store=` | за период: сумма, чеки, средний чек, в день, по магазинам/категориям/дням/месяцам (`days=N` или без параметров — всё время) |
| GET | `/api/expenses?from=&to=&store=` | записи расходов |
| GET | `/api/stores` | магазины |
| POST | `/api/sync?days=30` | забрать почту сейчас |
| GET/PUT | `/api/settings` * | настройки (секреты: только факт наличия; пусто = не менять, `__clear__` = отключить, `__reset__` = вернуть `.env`) |
| POST | `/api/settings/test-imap` * | проверка подключения (можно с несохранёнными значениями) |
| POST/PUT/DELETE | `/api/stores[/{id}]` * | магазины (удалить можно только магазин без расходов — иначе выключить) |
| POST | `/api/discover?days=90` * | скан ящика: кандидаты в магазины |
| GET | `/api/receipts/problems?days=30` * | не разобранные / отложенные чеки с текстом |
| POST | `/api/reprocess?confirm=yes[&force=yes][&days=N]` * | пересборка: заново скачать и разобрать письма всех *включённых* магазинов (выключенные не трогаются) |

Все перечисленные маршруты требуют `X-Admin-Token`, включая строки без прежней отметки `*`.
Единственный публичный API: `GET /api/live`, ответ только `{"ok":true}`.

### Документация

- [docs/DEPLOY.md](docs/DEPLOY.md) — deploying on a fresh Linux server (English)
- [docs/DEVNOTES.md](docs/DEVNOTES.md) — заметки для разработчика: модули, поток синка, настройки, тесты, ограничения
- [docs/REVIEW-2026-09-12.md](docs/REVIEW-2026-09-12.md) — все находки ревью, исправления, ограничения и миграции
- [docs/TESTING.md](docs/TESTING.md) — запуск регрессионных тестов без рабочей почты и базы

### Разработка

Тесты запускаются так же, как в английском разделе выше; рабочие почтовые credentials и базу не используйте в автоматических тестах.
# expense-tracker
# expense-tracker
