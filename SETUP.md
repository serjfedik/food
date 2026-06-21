# Setup — Google Drive + Sheets + опциональный Vision

Пошаговый чек-лист. Делается один раз. Без программирования.

---

## Шаг 1 · Сервисный аккаунт Google (нужно для всего)

Сервисный аккаунт — это «робот-аккаунт» Google, от имени которого
приложение будет читать и писать. Создаётся бесплатно.

1. Открыть https://console.cloud.google.com и войти под своим Google-аккаунтом.
2. Сверху — выпадашка проектов → **New Project** →
   название любое (например, `recipe-vault`) → **Create**.
3. В этом проекте включить два API:
   - **APIs & Services → Library** → найти **Google Drive API** → **Enable**.
   - Там же — найти **Google Sheets API** → **Enable**.
4. **IAM & Admin → Service Accounts → Create service account**:
   - Name: `recipe-vault-bot`
   - Role: можно оставить пустым (доступы выдадим через расшаривание папки/таблицы).
   - **Done**.
5. В созданном сервисном аккаунте — вкладка **Keys → Add Key → Create new key →
   JSON → Create**. На компьютер скачается файл `xxxx.json`.
   **Не теряйте его** — это «пароль» сервисного аккаунта.
6. В этом же JSON найдите поле `"client_email"` — оно вида
   `recipe-vault-bot@your-project.iam.gserviceaccount.com`. **Запомните его** —
   мы будем расшаривать ему папку и таблицу.

---

## Шаг 2 · Папка Google Drive для рецептов

В этой папке будут лежать:
- Google Doc на каждый рецепт (читать глазами).
- JSON-бэкап на каждый рецепт (для библиотеки и поиска).
- `meal_log.json` — дневник питания.
- `pantry.json` — холодильник.

1. Открыть https://drive.google.com.
2. **Создать → Папку** → название любое (например, `Recipe Vault`).
3. Открыть папку, в адресной строке скопировать **ID папки** —
   это длинная строка между `folders/` и концом URL:
   ```
   https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz
                                          ^^^^^^^^^^^^^^^^^^^^^^^^^^
                                          вот этот ID
   ```
4. Правым кликом по папке → **Поделиться** → вставить email сервисного аккаунта
   (из Шага 1.6) → роль **Editor** → **Send**. Появится предупреждение
   «уведомление не уйдёт» — нормально.

---

## Шаг 3 · Мастер-таблица Google Sheets (вторичная база знаний)

Таблица — для удобного просмотра/фильтра рецептов «глазами», без приложения.
Приложение само создаст вкладки **Рецепты**, **Дневник**, **Холодильник**
и наполнит их при первом сохранении.

1. Открыть https://sheets.new — создастся пустая таблица.
2. Название документа сверху — любое (например, `Recipe Vault · мастер-таблица`).
3. Скопировать **ID таблицы** из URL — между `/d/` и `/edit`:
   ```
   https://docs.google.com/spreadsheets/d/1XyZaBcDeFgHiJkLmNoPqRsTuVwX/edit
                                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                          вот этот ID
   ```
4. **Поделиться** (кнопка справа сверху) → вставить email сервисного аккаунта →
   роль **Editor** → **Send**.

> Если оставить таблицу неподключённой — приложение работает как раньше:
> рецепты пишутся только в Drive-папку. Sheets-вкладка — это бонус.

---

## Шаг 4 · Streamlit Cloud secrets

В вашем приложении на share.streamlit.io → **Settings → Secrets** —
вставить эту простыню, заменив значения на свои:

```toml
# ── секция 1 · содержимое JSON сервисного аккаунта (из Шага 1.5) ──
[gcp_service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "abc...123"
private_key = "-----BEGIN PRIVATE KEY-----\nMIIEv...\n-----END PRIVATE KEY-----\n"
client_email = "recipe-vault-bot@your-project.iam.gserviceaccount.com"
client_id = "1234567890"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/..."

# ── секция 2 · ID папки Drive (из Шага 2.3) ──
[google_drive]
folder_id = "1AbCdEfGhIjKlMnOpQrStUvWxYz"

# ── секция 3 · ID мастер-таблицы (из Шага 3.3) — опционально ──
[google_sheets]
spreadsheet_id = "1XyZaBcDeFgHiJkLmNoPqRsTuVwX"

# ── секция 4 · ключ Anthropic для Vision-распознавания фото — опционально ──
ANTHROPIC_API_KEY = "sk-ant-..."
```

**Подсказки по `private_key`:**
- Это многострочное поле. В TOML строку нужно либо обернуть в `"…"` и сохранить
  `\n` как литералы (как в примере выше — из JSON именно так и приходит),
  либо использовать тройные кавычки и реальные переносы строк.
- Самое простое: скопировать значение `private_key` из JSON-файла **как есть**
  и обернуть тройными кавычками:
  ```toml
  private_key = """-----BEGIN PRIVATE KEY-----
  MIIEv...
  -----END PRIVATE KEY-----
  """
  ```

После сохранения secrets Streamlit Cloud перезапустит приложение
автоматически. В сайдбаре должно появиться:
- **папка: 1AbCdEfGhIj…**
- **✓ Sheets синк: таблица** (ссылка)

---

## Что сохраняется куда

| Объект | Drive (папка) | Sheets (мастер-таблица) |
|---|---|---|
| Рецепт | Google Doc + `recipe-title.json` | строка во вкладке **Рецепты** |
| Дневник | `meal_log.json` | целиком — вкладка **Дневник** |
| Холодильник | `pantry.json` | целиком — вкладка **Холодильник** |

В Drive — каждый рецепт как отдельный файл (читать руками удобно).
В Sheets — все рецепты ровной таблицей (фильтр, сортировка, выгрузка в CSV).

---

## Частые ошибки

| Симптом | Что делать |
|---|---|
| `Не удалось открыть таблицу …` | Расшарьте таблицу с email сервисного аккаунта (Editor). |
| `Drive API has not been used` | В Cloud Console включить **Google Drive API**. |
| `Permission denied` при сохранении | То же — расшарьте папку Drive с email сервисного аккаунта. |
| `private_key parse error` | Перенесите ключ в тройные кавычки `"""…"""`. |
| Sheets-таблица пуста после сохранения | Откройте её — приложение само создало вкладки. Если нет — нажмите «обновить кэш» в сайдбаре. |

---

## Шаг 5 (опционально) · Anthropic для Vision

Только если нужна вкладка «фото холодильника (ai)»:

1. https://console.anthropic.com → зарегистрироваться.
2. **API Keys → Create Key** → скопировать `sk-ant-...`.
3. Положить на счёт **$5–10** (одно распознавание ≈ $0.005 на Haiku 4.5).
4. В Streamlit Secrets (см. секцию 4 выше) указать ключ.
5. Сохранить → приложение перезагрузится.
