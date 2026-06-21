# 🍲 Recipe Vault

Streamlit-приложение для оцифровки, хранения и анализа рецептов
с синхронизацией в Google Drive.

## Что умеет

- **Загрузка** рецепта в PDF, DOCX, фото и сканах (PNG/JPG/TIFF/WebP) или .txt.
- **OCR** для рукописных и сканированных рецептов (Tesseract, языки rus + eng).
- **Адаптация** в реальном времени: правка артефактов распознавания и структуры
  (название / категория / теги / порции / время / кухня / сложность / избранное /
  ингредиенты / шаги / заметки).
- **Синхронизация** с Google Drive: сохранение как Google Doc, опционально
  `.md` и JSON-бэкап структуры (нужен для библиотеки/поиска).
- **Главная** с плитками категорий (Супы, Салаты, Десерты …) и счётчиком рецептов
  в каждой, а также «Последние добавленные».
- **Умный поиск** по словам в названии, категории, тегах и ингредиентах
  с лёгкой морфологией для русского и нечётким матчем по difflib.
- **Калькулятор КБЖУ** на основе локальной БД ~180 продуктов
  (`data/nutrition_ru.csv`): парсит «свёкла 2 шт», «1/2 стакана сметаны», «300 г»,
  считает калории/Б/Ж/У на весь рецепт, на порцию и на 100 г, с возможностью
  масштабировать ингредиенты.
- **Дневник питания** «Что вы хотите/ели сегодня?»: дата + тип приёма + порции,
  свод КБЖУ за день и за последние 7 дней, хранится как `meal_log.json` в Drive.

## Локальный запуск

```bash
pip install -r requirements.txt
# Для OCR нужны системные пакеты (Ubuntu/Debian):
sudo apt-get install -y tesseract-ocr tesseract-ocr-rus tesseract-ocr-eng poppler-utils

streamlit run app.py
```

## Деплой на Streamlit Community Cloud

1. Залогиньтесь на [share.streamlit.io](https://share.streamlit.io) с GitHub-аккаунтом.
2. **New app** → выберите этот репозиторий, ветку и `app.py`.
3. Системные пакеты (`tesseract-ocr`, `poppler-utils` и др.) подхватятся из
   `packages.txt`; Python-зависимости — из `requirements.txt`.
4. В настройках приложения откройте **Settings → Secrets** и вставьте содержимое
   `.streamlit/secrets.toml.example`, подставив реальные значения.

## Подключение Google Drive

1. В [Google Cloud Console](https://console.cloud.google.com/) создайте проект (или
   используйте существующий) и включите **Google Drive API**.
2. **IAM & Admin → Service Accounts** → создайте сервисный аккаунт. Затем
   **Keys → Add Key → JSON** — скачайте ключ.
3. В Google Drive создайте папку для рецептов. Расшарьте её с email сервисного
   аккаунта (вид `your-sa@project-id.iam.gserviceaccount.com`) с ролью **Editor**.
4. Скопируйте ID папки из её URL (`drive.google.com/drive/folders/<FOLDER_ID>`).
5. Заполните Streamlit secrets по образцу `.streamlit/secrets.toml.example`:
   - секция `[gcp_service_account]` — поля из скачанного JSON;
   - секция `[google_drive]` → `folder_id`.

## Структура

```
food/
├── app.py                      # Streamlit UI: Главная / Редактор / Библиотека / Дневник
├── src/
│   ├── file_loader.py          # PDF / DOCX / image → текст
│   ├── ocr.py                  # Tesseract-обёртки (ленивые импорты)
│   ├── recipe_parser.py        # эвристика текст → Recipe (category/tags/favorite…)
│   ├── categories.py           # категории из data/categories.json
│   ├── search.py               # умный поиск с лёгкой морфологией
│   ├── nutrition.py            # парсер ингредиентов + калькулятор КБЖУ
│   ├── meal_log.py             # модель дневника питания
│   └── google_drive.py         # синхронизация с Drive (recipes + meal_log)
├── data/
│   ├── categories.json         # список плиток (эмодзи, лейбл, цвет)
│   └── nutrition_ru.csv        # ~180 продуктов: ккал/Б/Ж/У/вес шт.
├── requirements.txt
├── packages.txt                # системные пакеты для Streamlit Cloud
└── .streamlit/
    ├── config.toml
    └── secrets.toml.example
```

## Расширение базы продуктов

`data/nutrition_ru.csv` — обычный CSV. Колонки:

| name | aliases | kcal | protein | fat | carbs | piece_g |
|---|---|---|---|---|---|---|
| лук репчатый | лук\|луковица | 41 | 1.4 | 0.0 | 8.2 | 100 |

- `aliases` — алиасы через `|` (помогают поиску в БД).
- `piece_g` — вес одной штуки (для `2 шт`); пусто, если неприменимо.
- Числа — на 100 г.

После правки CSV сделайте «🔄 Обновить кэш» в сайдбаре.

## Резервное копирование репозитория

В репозитории настроен автоматический бэкап:

- **GitHub Actions cron** (`.github/workflows/cloud-backup.yml`) — ежедневный snapshot
  всех веток в git-теги вида `snapshot/YYYYMMDD-HHMM/<branch>`. 0 токенов модели.
- **Hook Claude Code** (`.claude/hooks/cloud-backup.sh`) — тот же снапшот на
  `SessionStart`/`SessionEnd` с троттлингом по интервалу.

Параметры (интервал, ретеншн, опциональное офсайт-зеркало) — в
`.claude/cloud-backup.conf`. Для офсайт-зеркала добавьте секрет `MIRROR_REMOTE`
в Settings → Secrets and variables → Actions.
