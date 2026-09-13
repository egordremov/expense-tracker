/* UI languages: en (default), ru, lt. Database values (categories) are stored in Russian and translated for display. */
const I18N = {
ru: {
  app_title: "Расходы из почты", settings: "Настройки ⚙", back: "← к расходам", settings_title: "Настройки",
  sync_btn: "Синхронизировать почту", syncing: "Синхронизирую…",
  preset_7: "последние 7 дней", preset_30: "последние 30 дней", preset_thisMonth: "этот месяц", preset_lastMonth: "прошлый месяц",
  preset_90: "последние 90 дней", preset_365: "последний год", preset_all: "всё время", preset_custom: "свой период",
  from: "с", to: "по", all_stores: "все магазины", all_categories: "все категории",
  period_line: "Период: <b>с {from} по {to}</b> — {days}", day_forms: ["день", "дня", "дней"],
  card_total: "Потрачено за период", card_receipts: "Чеков", card_avg: "Средний чек", card_perday: "В день",
  chart_stores: "По магазинам", chart_cats: "По категориям", chart_shares: "Доли категорий", chart_days: "По дням", chart_months: "По месяцам",
  th_date: "Дата", th_store: "Магазин", th_category: "Категория", th_description: "Описание", th_amount: "Сумма",
  table_info: "{period}: {n} записей, сумма {sum}", period_range: "с {from} по {to}", empty_period: "За этот период записей нет",
  last_sync_line: "последняя синхронизация: {when}; ", receipts_total: "чеков в базе всего: {n}", attention: "Внимание: ",
  error_prefix: "Ошибка: ",
  // statuses
  st_success: "успешно", st_partial: "частично", st_error: "ошибка", st_running: "выполняется", st_busy: "уже идёт", st_never: "ещё не было", st_skipped: "пропущен",
  trig_startup: "при старте", trig_schedule: "по расписанию", trig_retry: "повтор", trig_manual: "вручную", trig_reprocess: "пересборка",
  // sync result (details)
  sync_summary: "Писем за {days} дн.: {mails}{per_store}, новых: {new}, расходов добавлено: {expenses}{per_store_new}",
  sync_folder: "; папка {folder}", sync_retried: "; дозобрано ранее упавших: {n}", sync_dup: "; писем об уже учтённых заказах: {n}",
  sync_superseded: "; уточнено по более подробному письму: {n}", sync_unparsed: "; чеков не разобрано: {n}", sync_suspicious: "; чеков с несходящимся итогом: {n}",
  sync_failed: "; с ошибкой: {n} (повторим при следующем синке)", sync_gave_up: "; отложено после {max} неудач: {n}", sync_busy: "синхронизация уже идёт",
  // health
  h_imap_not_configured: "почта не настроена (IMAP пользователь/пароль)", h_no_success_yet: "успешных сборов ещё не было",
  h_stale: "нет успешного сбора больше {hours} ч", h_last_error: "последний синк с ошибкой: {message}", h_folder_warning: "{text}",
  h_secrets_broken: "файл секретов data/secrets.json не читается — пароль почты и ключи из него не применяются",
  h_reprocess_pending: "пересборка базы не завершилась — история досбирается при следующих синках", h_no_stores: "нет включённых магазинов",
  h_unparsed: "за 30 дней {n} чек(ов) не разобрано — смотрите «Проблемные чеки» в настройках",
  h_failed: "за 30 дней {n} письм(а) отложено после повторных ошибок разбора", h_failed_pending: "{n} письм(а) ждут повторного разбора",
  h_no_receipts: "новых чеков не было {days} дней (последний {last}) — письма перестали приходить или попадают в спам?",
  h_db_error: "база недоступна: {error}",
  health_ok: "Всё в порядке. ", health_problems: "Проблемы: ", no_token_warn: "Токен администратора не задан. Доступ к API закрыт. ",
  schedule_line: "Расписание: {schedule}. Последний синк: {status}{when}{next}", sched_daily: "ежедневно в {time}", sched_every: "каждые {n} мин",
  at_time: " в {when}", next_sync: "; следующий: {next}",
  // settings sections
  sec_mail: "Почта (IMAP)", sec_stores: "Магазины и отправители", sec_schedule: "Расписание и надёжность", sec_claude: "Claude (необязательно)",
  sec_access: "Доступ", sec_maint: "Обслуживание", sec_journal: "Журнал синхронизаций", sec_problems: "Проблемные чеки (30 дней)",
  l_host: "Сервер", l_user: "Пользователь (адрес ящика)", l_password: "Пароль", l_folder: "Папка", l_timeout: "Таймаут соединения, с",
  ph_password: "оставьте пустым, чтобы не менять", ph_folder: "пусто = Gmail «Вся почта» / INBOX",
  hint_gmail: "Gmail: нужен <a href=\"https://myaccount.google.com/apppasswords\" target=\"_blank\">пароль приложения</a>, не пароль аккаунта.",
  test_conn: "Проверить подключение", testing: "проверяю…", test_ok: "вход выполнен", test_folder: ", папка «{folder}»", test_mails: "; писем за {days} дн.: ",
  stores_hint: "Отправители: полный адрес или домен, например <code>receipts@shop.lt</code>, <code>maxima.lt</code>, <code>wolt.com</code>. Домены включают поддомены; отображаемое имя не учитывается.",
  th_enabled: "Вкл.", th_name: "Название", th_senders: "Отправители (через запятую)", th_parser: "Разбор", th_defcat: "Категория для всех покупок",
  ph_store_name: "Wolt", ph_senders: "wolt.com, order.site", ph_defcat: "пусто = по позициям", save: "Сохранить", add_store: "+ Добавить магазин",
  discover: "Найти в почте", d_60: "за 60 дней", d_90: "за 90 дней", d_180: "за 180 дней", d_365: "за год",
  discovering: "сканирую почту, это может занять пару минут…", discover_info: "просмотрено {scanned} писем за {days} дн.{trunc}, кандидатов: {n}",
  discover_trunc: " (не все — уменьшите период)", th_sender: "Отправитель", th_mails: "Писем", th_pdf: "PDF", th_subjects: "Темы", already: "уже есть", add: "Добавить",
  store_saved: "Магазин «{name}» сохранён. Чтобы разобрать его старые письма — «Пересобрать всё из почты» или «Синхронизировать за год».",
  confirm_delete_store: "Удалить магазин? (магазин с уже разобранными письмами удалить нельзя — его можно выключить)",
  l_daily: "Ежедневно в (ЧЧ:ММ; пусто — по интервалу)", l_interval: "Интервал, мин (если время не задано)", l_retry_min: "Повтор при ошибке через, мин",
  l_retry_max: "Повторов максимум", l_timeout_min: "Таймаут одного синка, мин", l_stale: "Тревога, если нет успешного сбора, ч",
  l_no_receipts: "Тревога, если нет новых чеков, дней", l_window: "Окно выборки почты, дней", l_window_max: "Окно максимум, дней", l_max_failed: "Попыток разбора письма до «отложить»",
  l_api_key: "API-ключ", l_model: "Модель",
  hint_claude: "С ключом: разбор чеков магазинов без своего парсера по позициям и нормальный перевод названий. Без ключа: Maxima, Wolt/order.site и итоги остальных писем.",
  l_admin_token: "Токен администратора",
  hint_token: "Токен обязателен. Новый токен: минимум 32 печатных ASCII-символа без пробелов. Очистка запрещена.",
  save_settings: "Сохранить настройки", clear_on_save: "Стереть при сохранении:", clr_password: "пароль почты", clr_key: "ключ Claude", clr_token: "токен администратора",
  sync_now: "Синхронизировать", s_30: "за 30 дней", s_90: "за 90 дней", s_365: "за год", reprocess: "Пересобрать всё из почты",
  hint_reprocess: "Пересборка удаляет разобранные расходы включённых магазинов и собирает их заново по текущим парсерам — нужна после добавления магазинов или смены парсеров. Копия базы делается автоматически (data/backup).",
  th_when: "Когда", th_who: "Кто", th_status: "Статус", th_message: "Сообщение", journal_empty: "пока пусто",
  problems_none: "Нет — все чеки за 30 дней разобраны.", mode_failed: "отложено после ошибок", mode_unparsed: "не разобрано", no_text: "(текст не сохранён)",
  src_db: "сохранено здесь", src_env: "из .env", src_default: "по умолчанию", src_secrets: "сохранено здесь", set_yes: "задан ✓", set_no: "не задан",
  no_changes: "Изменений нет", saved: "Сохранено. Расписание применено без перезапуска.", load_failed: "Не удалось загрузить настройки: ",
  confirm_clear: "Стереть: {what}?", clr_desc_password: "пароль почты (сбор остановится)", clr_desc_key: "ключ Claude", clr_desc_token: "токен администратора",
  prompt_token: "Токен администратора:", no_token: "нет токена",
  confirm_reprocess: "Пересобрать все расходы из почты? Текущие записи будут удалены и собраны заново (копия базы сохранится).", reprocessing: "Пересобираю — это может занять несколько минут…",
  secret_keep: "не менять", secret_clear: "стереть (и не брать из .env)", secret_reset: "вернуть значение из .env", secret_action: "При сохранении:",
  src_secrets_null: "стёрто (значение из .env не используется)",
  lang: "Язык",
},
en: {
  app_title: "Expenses from e-mail", settings: "Settings ⚙", back: "← back to expenses", settings_title: "Settings",
  sync_btn: "Synchronise mail", syncing: "Synchronising…",
  preset_7: "last 7 days", preset_30: "last 30 days", preset_thisMonth: "this month", preset_lastMonth: "last month",
  preset_90: "last 90 days", preset_365: "last year", preset_all: "all time", preset_custom: "custom range",
  from: "from", to: "to", all_stores: "all stores", all_categories: "all categories",
  period_line: "Period: <b>{from} – {to}</b> — {days}", day_forms: ["day", "days", "days"],
  card_total: "Spent in period", card_receipts: "Receipts", card_avg: "Average receipt", card_perday: "Per day",
  chart_stores: "By store", chart_cats: "By category", chart_shares: "Category shares", chart_days: "By day", chart_months: "By month",
  th_date: "Date", th_store: "Store", th_category: "Category", th_description: "Description", th_amount: "Amount",
  table_info: "{period}: {n} records, total {sum}", period_range: "{from} – {to}", empty_period: "No records in this period",
  last_sync_line: "last synchronisation: {when}; ", receipts_total: "receipts in database: {n}", attention: "Attention: ",
  error_prefix: "Error: ",
  st_success: "success", st_partial: "partial", st_error: "error", st_running: "running", st_busy: "already running", st_never: "never", st_skipped: "skipped",
  trig_startup: "on start", trig_schedule: "scheduled", trig_retry: "retry", trig_manual: "manual", trig_reprocess: "rebuild",
  sync_summary: "Mails in {days} days: {mails}{per_store}, new: {new}, expenses added: {expenses}{per_store_new}",
  sync_folder: "; folder {folder}", sync_retried: "; previously failed mails now parsed: {n}", sync_dup: "; mails about already counted orders: {n}",
  sync_superseded: "; refined from a more detailed mail: {n}", sync_unparsed: "; receipts not parsed: {n}", sync_suspicious: "; receipts with mismatching total: {n}",
  sync_failed: "; with errors: {n} (will retry next sync)", sync_gave_up: "; deferred after {max} failures: {n}", sync_busy: "a synchronisation is already running",
  h_imap_not_configured: "mail is not configured (IMAP user/password)", h_no_success_yet: "no successful synchronisation yet",
  h_stale: "no successful synchronisation for more than {hours} h", h_last_error: "last synchronisation failed: {message}", h_folder_warning: "{text}",
  h_secrets_broken: "the secrets file data/secrets.json cannot be read — the mail password and keys from it are not applied",
  h_reprocess_pending: "the database rebuild did not finish — history is being completed on the next synchronisations", h_no_stores: "no enabled stores",
  h_unparsed: "{n} receipt(s) could not be parsed in the last 30 days — see “Problem receipts” in settings",
  h_failed: "{n} mail(s) deferred after repeated parsing errors in the last 30 days", h_failed_pending: "{n} mail(s) waiting to be parsed again",
  h_no_receipts: "no new receipts for {days} days (last one {last}) — have the mails stopped coming or landed in spam?",
  h_db_error: "database unavailable: {error}",
  health_ok: "All good. ", health_problems: "Problems: ", no_token_warn: "No admin token is set. API access is closed. ",
  schedule_line: "Schedule: {schedule}. Last synchronisation: {status}{when}{next}", sched_daily: "daily at {time}", sched_every: "every {n} min",
  at_time: " at {when}", next_sync: "; next: {next}",
  sec_mail: "Mail (IMAP)", sec_stores: "Stores and senders", sec_schedule: "Schedule and reliability", sec_claude: "Claude (optional)",
  sec_access: "Access", sec_maint: "Maintenance", sec_journal: "Synchronisation journal", sec_problems: "Problem receipts (30 days)",
  l_host: "Server", l_user: "User (mailbox address)", l_password: "Password", l_folder: "Folder", l_timeout: "Connection timeout, s",
  ph_password: "leave empty to keep the current one", ph_folder: "empty = Gmail “All Mail” / INBOX",
  hint_gmail: "Gmail: use an <a href=\"https://myaccount.google.com/apppasswords\" target=\"_blank\">app password</a>, not the account password.",
  test_conn: "Test connection", testing: "testing…", test_ok: "login OK", test_folder: ", folder “{folder}”", test_mails: "; mails in {days} days: ",
  stores_hint: "Senders: full addresses or domains, such as <code>receipts@shop.lt</code>, <code>maxima.lt</code>, <code>wolt.com</code>. Domains include subdomains; display names are ignored.",
  th_enabled: "On", th_name: "Name", th_senders: "Senders (comma-separated)", th_parser: "Parser", th_defcat: "Category for all purchases",
  ph_store_name: "Wolt", ph_senders: "wolt.com, order.site", ph_defcat: "empty = per line item", save: "Save", add_store: "+ Add store",
  discover: "Find in mailbox", d_60: "last 60 days", d_90: "last 90 days", d_180: "last 180 days", d_365: "last year",
  discovering: "scanning the mailbox, this may take a couple of minutes…", discover_info: "{scanned} mails scanned over {days} days{trunc}, candidates: {n}",
  discover_trunc: " (not all — shorten the period)", th_sender: "Sender", th_mails: "Mails", th_pdf: "PDF", th_subjects: "Subjects", already: "already added", add: "Add",
  store_saved: "Store “{name}” saved. To parse its older mails use “Rebuild from mail” or “Synchronise — last year”.",
  confirm_delete_store: "Delete the store? (a store with parsed mails cannot be deleted — disable it instead)",
  l_daily: "Daily at (HH:MM; empty — by interval)", l_interval: "Interval, min (if no time is set)", l_retry_min: "Retry after error in, min",
  l_retry_max: "Max retries", l_timeout_min: "Timeout of one sync, min", l_stale: "Alert if no successful sync for, h",
  l_no_receipts: "Alert if no new receipts for, days", l_window: "Mail fetch window, days", l_window_max: "Window maximum, days", l_max_failed: "Parse attempts before deferring a mail",
  l_api_key: "API key", l_model: "Model",
  hint_claude: "With a key: itemised parsing of receipts from stores without a dedicated parser and proper translation of item names. Without it: Maxima, Wolt/order.site and totals of other mails.",
  l_admin_token: "Admin token",
  hint_token: "Token required. New token: at least 32 printable ASCII characters without spaces. Clearing is disabled.",
  save_settings: "Save settings", clear_on_save: "Erase on save:", clr_password: "mail password", clr_key: "Claude key", clr_token: "admin token",
  sync_now: "Synchronise", s_30: "last 30 days", s_90: "last 90 days", s_365: "last year", reprocess: "Rebuild from mail",
  hint_reprocess: "The rebuild deletes the parsed expenses of enabled stores and collects them again with the current parsers — needed after adding stores or changing parsers. A database copy is made automatically (data/backup).",
  th_when: "When", th_who: "Trigger", th_status: "Status", th_message: "Message", journal_empty: "nothing yet",
  problems_none: "None — all receipts of the last 30 days are parsed.", mode_failed: "deferred after errors", mode_unparsed: "not parsed", no_text: "(text not stored)",
  src_db: "saved here", src_env: "from .env", src_default: "default", src_secrets: "saved here", set_yes: "set ✓", set_no: "not set",
  no_changes: "Nothing changed", saved: "Saved. The schedule is applied without a restart.", load_failed: "Could not load settings: ",
  confirm_clear: "Erase: {what}?", clr_desc_password: "mail password (collection will stop)", clr_desc_key: "Claude key", clr_desc_token: "admin token",
  prompt_token: "Admin token:", no_token: "no token",
  confirm_reprocess: "Rebuild all expenses from mail? Current records will be deleted and collected again (a database copy is kept).", reprocessing: "Rebuilding — this may take several minutes…",
  secret_keep: "keep", secret_clear: "erase (and ignore .env)", secret_reset: "restore the value from .env", secret_action: "On save:",
  src_secrets_null: "erased (the .env value is ignored)",
  lang: "Language",
},
lt: {
  app_title: "Išlaidos iš el. pašto", settings: "Nustatymai ⚙", back: "← į išlaidas", settings_title: "Nustatymai",
  sync_btn: "Sinchronizuoti paštą", syncing: "Sinchronizuojama…",
  preset_7: "paskutinės 7 dienos", preset_30: "paskutinės 30 dienų", preset_thisMonth: "šis mėnuo", preset_lastMonth: "praėjęs mėnuo",
  preset_90: "paskutinės 90 dienų", preset_365: "paskutiniai metai", preset_all: "visas laikas", preset_custom: "savas laikotarpis",
  from: "nuo", to: "iki", all_stores: "visos parduotuvės", all_categories: "visos kategorijos",
  period_line: "Laikotarpis: <b>nuo {from} iki {to}</b> — {days}", day_forms: ["diena", "dienos", "dienų"],
  card_total: "Išleista per laikotarpį", card_receipts: "Kvitų", card_avg: "Vidutinis kvitas", card_perday: "Per dieną",
  chart_stores: "Pagal parduotuves", chart_cats: "Pagal kategorijas", chart_shares: "Kategorijų dalys", chart_days: "Pagal dienas", chart_months: "Pagal mėnesius",
  th_date: "Data", th_store: "Parduotuvė", th_category: "Kategorija", th_description: "Aprašymas", th_amount: "Suma",
  table_info: "{period}: {n} įrašų, suma {sum}", period_range: "nuo {from} iki {to}", empty_period: "Šiuo laikotarpiu įrašų nėra",
  last_sync_line: "paskutinė sinchronizacija: {when}; ", receipts_total: "kvitų duomenų bazėje: {n}", attention: "Dėmesio: ",
  error_prefix: "Klaida: ",
  st_success: "sėkmingai", st_partial: "iš dalies", st_error: "klaida", st_running: "vykdoma", st_busy: "jau vykdoma", st_never: "dar nebuvo", st_skipped: "praleista",
  trig_startup: "paleidus", trig_schedule: "pagal tvarkaraštį", trig_retry: "pakartojimas", trig_manual: "rankiniu būdu", trig_reprocess: "perrinkimas",
  sync_summary: "Laiškų per {days} d.: {mails}{per_store}, naujų: {new}, pridėta išlaidų: {expenses}{per_store_new}",
  sync_folder: "; aplankas {folder}", sync_retried: "; išnagrinėta anksčiau nepavykusių: {n}", sync_dup: "; laiškų apie jau įskaitytus užsakymus: {n}",
  sync_superseded: "; patikslinta pagal išsamesnį laišką: {n}", sync_unparsed: "; neišnagrinėtų kvitų: {n}", sync_suspicious: "; kvitų su nesutampančia suma: {n}",
  sync_failed: "; su klaida: {n} (pakartosime kitą kartą)", sync_gave_up: "; atidėta po {max} nesėkmių: {n}", sync_busy: "sinchronizacija jau vykdoma",
  h_imap_not_configured: "paštas nesukonfigūruotas (IMAP vartotojas/slaptažodis)", h_no_success_yet: "sėkmingų sinchronizacijų dar nebuvo",
  h_stale: "sėkmingos sinchronizacijos nebuvo daugiau nei {hours} val.", h_last_error: "paskutinė sinchronizacija su klaida: {message}", h_folder_warning: "{text}",
  h_secrets_broken: "paslapčių failas data/secrets.json neperskaitomas — pašto slaptažodis ir raktai iš jo netaikomi",
  h_reprocess_pending: "duomenų bazės perrinkimas nebaigtas — istorija surenkama per kitas sinchronizacijas", h_no_stores: "nėra įjungtų parduotuvių",
  h_unparsed: "per 30 dienų neišnagrinėta kvitų: {n} — žr. „Problematiški kvitai“ nustatymuose",
  h_failed: "per 30 dienų atidėta laiškų po pakartotinių klaidų: {n}", h_failed_pending: "laiškų laukia pakartotinio nagrinėjimo: {n}",
  h_no_receipts: "naujų kvitų nebuvo {days} dienų (paskutinis {last}) — laiškai nebeateina ar patenka į šlamštą?",
  h_db_error: "duomenų bazė nepasiekiama: {error}",
  health_ok: "Viskas gerai. ", health_problems: "Problemos: ", no_token_warn: "Administratoriaus raktas nenustatytas. API prieiga uždaryta. ",
  schedule_line: "Tvarkaraštis: {schedule}. Paskutinė sinchronizacija: {status}{when}{next}", sched_daily: "kasdien {time}", sched_every: "kas {n} min.",
  at_time: " {when}", next_sync: "; kita: {next}",
  sec_mail: "Paštas (IMAP)", sec_stores: "Parduotuvės ir siuntėjai", sec_schedule: "Tvarkaraštis ir patikimumas", sec_claude: "Claude (neprivaloma)",
  sec_access: "Prieiga", sec_maint: "Priežiūra", sec_journal: "Sinchronizacijų žurnalas", sec_problems: "Problematiški kvitai (30 dienų)",
  l_host: "Serveris", l_user: "Vartotojas (pašto adresas)", l_password: "Slaptažodis", l_folder: "Aplankas", l_timeout: "Ryšio laukimo laikas, s",
  ph_password: "palikite tuščią, kad nekeistumėte", ph_folder: "tuščia = Gmail „Visas paštas“ / INBOX",
  hint_gmail: "Gmail: reikia <a href=\"https://myaccount.google.com/apppasswords\" target=\"_blank\">programos slaptažodžio</a>, ne paskyros slaptažodžio.",
  test_conn: "Tikrinti ryšį", testing: "tikrinama…", test_ok: "prisijungta", test_folder: ", aplankas „{folder}“", test_mails: "; laiškų per {days} d.: ",
  stores_hint: "Siuntėjai: pilni adresai arba domenai, pvz. <code>receipts@shop.lt</code>, <code>maxima.lt</code>, <code>wolt.com</code>. Įtraukiami subdomenai; rodomas vardas ignoruojamas.",
  th_enabled: "Įj.", th_name: "Pavadinimas", th_senders: "Siuntėjai (per kablelį)", th_parser: "Nagrinėjimas", th_defcat: "Kategorija visiems pirkiniams",
  ph_store_name: "Wolt", ph_senders: "wolt.com, order.site", ph_defcat: "tuščia = pagal pozicijas", save: "Išsaugoti", add_store: "+ Pridėti parduotuvę",
  discover: "Ieškoti pašte", d_60: "per 60 dienų", d_90: "per 90 dienų", d_180: "per 180 dienų", d_365: "per metus",
  discovering: "skenuojamas paštas, tai gali užtrukti porą minučių…", discover_info: "peržiūrėta {scanned} laiškų per {days} d.{trunc}, kandidatų: {n}",
  discover_trunc: " (ne visi — sutrumpinkite laikotarpį)", th_sender: "Siuntėjas", th_mails: "Laiškų", th_pdf: "PDF", th_subjects: "Temos", already: "jau yra", add: "Pridėti",
  store_saved: "Parduotuvė „{name}“ išsaugota. Kad būtų išnagrinėti senesni jos laiškai — „Perrinkti viską iš pašto“ arba „Sinchronizuoti — metai“.",
  confirm_delete_store: "Ištrinti parduotuvę? (parduotuvės su išnagrinėtais laiškais ištrinti negalima — ją galima išjungti)",
  l_daily: "Kasdien (VV:MM; tuščia — pagal intervalą)", l_interval: "Intervalas, min. (jei laikas nenurodytas)", l_retry_min: "Pakartoti po klaidos per, min.",
  l_retry_max: "Daugiausia pakartojimų", l_timeout_min: "Vienos sinchronizacijos limitas, min.", l_stale: "Įspėjimas, jei nėra sėkmingo surinkimo, val.",
  l_no_receipts: "Įspėjimas, jei nėra naujų kvitų, dienų", l_window: "Pašto atrankos langas, dienų", l_window_max: "Lango maksimumas, dienų", l_max_failed: "Laiško nagrinėjimo bandymų iki atidėjimo",
  l_api_key: "API raktas", l_model: "Modelis",
  hint_claude: "Su raktu: kvitų iš parduotuvių be savo nagrinėtuvo skaidymas pagal pozicijas ir normalus pavadinimų vertimas. Be rakto: Maxima, Wolt/order.site ir kitų laiškų sumos.",
  l_admin_token: "Administratoriaus raktas",
  hint_token: "Raktas privalomas. Naujas raktas: bent 32 spausdinami ASCII simboliai be tarpų. Ištrinti negalima.",
  save_settings: "Išsaugoti nustatymus", clear_on_save: "Ištrinti išsaugant:", clr_password: "pašto slaptažodį", clr_key: "Claude raktą", clr_token: "administratoriaus raktą",
  sync_now: "Sinchronizuoti", s_30: "per 30 dienų", s_90: "per 90 dienų", s_365: "per metus", reprocess: "Perrinkti viską iš pašto",
  hint_reprocess: "Perrinkimas ištrina įjungtų parduotuvių išnagrinėtas išlaidas ir surenka jas iš naujo pagal dabartinius nagrinėtuvus — reikia pridėjus parduotuvių ar pakeitus nagrinėtuvus. Duomenų bazės kopija daroma automatiškai (data/backup).",
  th_when: "Kada", th_who: "Kas", th_status: "Būsena", th_message: "Pranešimas", journal_empty: "kol kas tuščia",
  problems_none: "Nėra — visi 30 dienų kvitai išnagrinėti.", mode_failed: "atidėta po klaidų", mode_unparsed: "neišnagrinėta", no_text: "(tekstas neišsaugotas)",
  src_db: "išsaugota čia", src_env: "iš .env", src_default: "pagal nutylėjimą", src_secrets: "išsaugota čia", set_yes: "nustatytas ✓", set_no: "nenustatytas",
  no_changes: "Pakeitimų nėra", saved: "Išsaugota. Tvarkaraštis pritaikytas be perkrovimo.", load_failed: "Nepavyko įkelti nustatymų: ",
  confirm_clear: "Ištrinti: {what}?", clr_desc_password: "pašto slaptažodį (surinkimas sustos)", clr_desc_key: "Claude raktą", clr_desc_token: "administratoriaus raktą",
  prompt_token: "Administratoriaus raktas:", no_token: "nėra rakto",
  confirm_reprocess: "Perrinkti visas išlaidas iš pašto? Dabartiniai įrašai bus ištrinti ir surinkti iš naujo (duomenų bazės kopija išsaugoma).", reprocessing: "Perrenkama — tai gali užtrukti kelias minutes…",
  secret_keep: "nekeisti", secret_clear: "ištrinti (ir nenaudoti .env)", secret_reset: "grąžinti reikšmę iš .env", secret_action: "Išsaugant:",
  src_secrets_null: "ištrinta (.env reikšmė nenaudojama)",
  lang: "Kalba",
}};

/* Categories are stored in Russian and translated for display. */
const CATS_I18N = {
  "продукты": ["groceries", "maisto prekės"], "мясо и рыба": ["meat & fish", "mėsa ir žuvis"], "молочное и яйца": ["dairy & eggs", "pieno produktai ir kiaušiniai"],
  "овощи и фрукты": ["fruit & vegetables", "vaisiai ir daržovės"], "хлеб и бакалея": ["bread & pantry", "duona ir bakalėja"],
  "сладости и снеки": ["sweets & snacks", "saldumynai ir užkandžiai"], "напитки": ["drinks", "gėrimai"], "алкоголь": ["alcohol", "alkoholis"],
  "бытовая химия": ["household chemicals", "buitinė chemija"], "гигиена и косметика": ["hygiene & cosmetics", "higiena ir kosmetika"],
  "дети": ["kids", "vaikams"], "дом и прочее": ["home & other", "namams ir kita"], "пакеты и залог": ["bags & deposit", "maišeliai ir tara"],
  "скидки и бонусы": ["discounts & bonuses", "nuolaidos ir bonusai"], "рестораны и доставка": ["restaurants & delivery", "restoranai ir pristatymas"],
  "техника и дом": ["electronics & home", "technika ir namai"], "коммунальные и связь": ["utilities & telecom", "komunalinės paslaugos ir ryšys"],
  "подписки": ["subscriptions", "prenumeratos"], "транспорт": ["transport", "transportas"], "одежда и спорт": ["clothing & sport", "apranga ir sportas"],
  "здоровье": ["health", "sveikata"], "прочее": ["other", "kita"],
};
const LANGS = ["ru", "en", "lt"], DEFAULT_LANG = "en", LOCALES = { ru: "ru-RU", en: "en-GB", lt: "lt-LT" };
function savedLangFromCookie() {
  try {
    const m = document.cookie.match(/(?:^|;\s*)lang=([^;]+)/);
    const s = m && decodeURIComponent(m[1]);
    if (LANGS.includes(s)) return s;
  } catch (e) {}
  return "";
}
const LANG = (() => {
  const c = savedLangFromCookie(); if (c) return c;
  try { const s = localStorage.getItem("lang"); if (LANGS.includes(s)) return s; } catch (e) {}
  return DEFAULT_LANG;
})();
document.documentElement.lang = LANG;
function t(key, params) { let s = (I18N[LANG] && I18N[LANG][key]) ?? I18N.ru[key] ?? key; if (params) for (const k in params) s = s.split("{" + k + "}").join(params[k]); return s; }
function setLang(l) {
  try { localStorage.setItem("lang", l); } catch (e) {}
  try { document.cookie = "lang=" + encodeURIComponent(l) + "; Max-Age=31536000; Path=/; SameSite=Lax"; } catch (e) {}
  location.reload();
}
function plural(n, forms) {                       // day forms: ru uses forms for 1/2/5, lt for 1/2/10, en for singular/plural
  n = Math.abs(n); const m10 = n % 10, m100 = n % 100;
  if (LANG === "en") return n === 1 ? forms[0] : forms[1];
  if (LANG === "lt") return (m10 === 1 && m100 !== 11) ? forms[0] : (m10 >= 2 && m10 <= 9 && (m100 < 10 || m100 >= 20)) ? forms[1] : forms[2];
  return (m10 === 1 && m100 !== 11) ? forms[0] : (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) ? forms[1] : forms[2];
}
const eur = v => (v || 0).toLocaleString(LOCALES[LANG], { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";
const fmtDate = s => new Date(s.length <= 10 ? s + "T00:00:00" : s).toLocaleDateString(LOCALES[LANG]);
const fmtDateTime = s => new Date(s).toLocaleString(LOCALES[LANG]);
const catName = ru => { const m = CATS_I18N[ru]; return LANG === "ru" || !m ? ru : (LANG === "en" ? m[0] : m[1]); };
const catKey = shown => { if (!shown) return ""; for (const ru in CATS_I18N) { if (shown === ru || shown === CATS_I18N[ru][0] || shown === CATS_I18N[ru][1]) return ru; } return shown; };
const statusName = s => t("st_" + s) === "st_" + s ? s : t("st_" + s);
const triggerName = s => t("trig_" + s) === "trig_" + s ? s : t("trig_" + s);
/* Item descriptions: en/lt show the original receipt text (Lithuanian), with the Russian translation in a tooltip. */
function descriptionOf(e) { if (LANG === "ru") return [e.description, e.description_lt || ""]; return [e.description_lt || e.description, e.description_lt ? e.description : ""]; }
/* Sync result: localized from structured details, or displayed as preformatted text. */
function syncMessage(run) {
  const d = run.details; if (!d || run.status === "error") return run.message || (run.status === "busy" ? t("sync_busy") : "");
  const ps = d.per_store && Object.keys(d.per_store).length ? " (" + Object.entries(d.per_store).sort((a, b) => b[1] - a[1]).map(([k, v]) => k + ": " + v).join(", ") + ")" : "";
  const psn = d.per_store_new && Object.keys(d.per_store_new).length ? " (" + Object.entries(d.per_store_new).map(([k, v]) => k + ": " + v).join(", ") + ")" : "";
  let s = t("sync_summary", { days: d.days, mails: d.mails, per_store: ps, new: d.new_mails, expenses: d.new_expenses, per_store_new: psn });
  if (d.folder && d.folder !== "INBOX") s += t("sync_folder", { folder: d.folder });
  if (d.warning) s += "; " + d.warning;
  if (d.retried_ok) s += t("sync_retried", { n: d.retried_ok });
  if (d.dup) s += t("sync_dup", { n: d.dup });
  if (d.superseded) s += t("sync_superseded", { n: d.superseded });
  if (d.unparsed) s += t("sync_unparsed", { n: d.unparsed });
  if (d.suspicious) s += t("sync_suspicious", { n: d.suspicious });
  if (d.failed) s += t("sync_failed", { n: d.failed });
  if (d.gave_up) s += t("sync_gave_up", { n: d.gave_up, max: d.max_attempts });
  return s;
}
function healthProblems(h) { if (Array.isArray(h.problems_i18n) && h.problems_i18n.length) return h.problems_i18n.map(p => t("h_" + p.code, p.params || {})); return h.problems || []; }
function scheduleName(h) { return h.schedule_i18n ? (h.schedule_i18n.daily ? t("sched_daily", { time: h.schedule_i18n.daily }) : t("sched_every", { n: h.schedule_i18n.every })) : h.schedule; }
/* Markup: data-i18n (text/HTML), data-i18n-ph (placeholder), data-i18n-title. */
function applyI18n() {
  document.querySelectorAll("[data-i18n]").forEach(el => { el.innerHTML = t(el.dataset.i18n); });
  document.querySelectorAll("[data-i18n-ph]").forEach(el => { el.placeholder = t(el.dataset.i18nPh); });
  document.querySelectorAll("[data-i18n-title]").forEach(el => { el.title = t(el.dataset.i18nTitle); });
  document.querySelectorAll("select.langSel").forEach(sel => { sel.value = LANG; sel.onchange = () => setLang(sel.value); });
  document.title = t(document.body.dataset.titleKey || "app_title");
}
