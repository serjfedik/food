"""Recipe Vault — Streamlit-приложение для оцифровки и хранения рецептов.

Страницы:
- Главная: плитки категорий + умный поиск.
- Редактор: загрузка (PDF/DOCX/фото с OCR) → адаптация → сохранение в Google Drive.
- Библиотека: список рецептов из папки Drive с фильтрами и панелью КБЖУ.
- Дневник: «Что вы хотите сегодня?» — лог съеденного с расчётом КБЖУ за день.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime
from typing import Any, Optional

import streamlit as st

from src import categories as cats
from src.file_loader import LoadResult, SUPPORTED_EXTS, load_file
from src.google_drive import DriveClient, DriveError
from src.meal_log import MEAL_TYPES, MealEntry, MealLog
from src.nutrition import (Nutrition, calc_recipe, load_products, parse_servings)
from src.recipe_parser import Recipe, parse_recipe
from src.search import search as search_recipes


st.set_page_config(
    page_title="Recipe Vault",
    page_icon="🍲",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

def _init_state() -> None:
    defaults: dict[str, Any] = {
        "page": "home",
        "editor_stage": "upload",
        "raw_text": "",
        "load_meta": None,
        "recipe": Recipe(),
        "last_filename": "",
        "saved_links": [],
        "selected_category": "",
        "search_query": "",
        "favorites_only": False,
        "selected_recipe_id": "",
        "diary_date": date.today(),
        "diary_meal_type": "обед",
        "diary_portions": 1.0,
        "scaler_factor": 1.0,
        "meal_log": None,
        "meal_log_file_id": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


_init_state()


# ---------------------------------------------------------------------------
# Drive helpers
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def _get_drive_client() -> Optional[DriveClient]:
    if "gcp_service_account" not in st.secrets or "google_drive" not in st.secrets:
        return None
    folder_id = st.secrets["google_drive"].get("folder_id", "")
    sa = dict(st.secrets["gcp_service_account"])
    try:
        return DriveClient(sa, folder_id=folder_id)
    except DriveError as exc:
        st.sidebar.error(f"Google Drive: {exc}")
        return None


@st.cache_data(show_spinner=False, ttl=120)
def _cached_library(_client_token: str) -> list[dict[str, Any]]:
    client = _get_drive_client()
    if client is None:
        return []
    return client.list_recipe_jsons()


def _invalidate_library() -> None:
    _cached_library.clear()


def _recipes_from_library(library: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Раскрываем payload в плоский dict рецепта с полями для поиска и UI."""
    flat: list[dict[str, Any]] = []
    for item in library:
        recipe_dict = item["payload"].get("recipe") or {}
        if not recipe_dict:
            continue
        flat.append({
            **recipe_dict,
            "_file_id": item["file_id"],
            "_file_name": item["name"],
            "_modified": item["modified"],
            "_web_link": item["web_link"],
        })
    return flat


# ---------------------------------------------------------------------------
# Meal log helpers
# ---------------------------------------------------------------------------

def _ensure_meal_log() -> tuple[MealLog, DriveClient | None]:
    client = _get_drive_client()
    if st.session_state.meal_log is None:
        if client is None:
            st.session_state.meal_log = MealLog()
        else:
            try:
                payload, file_id = client.load_meal_log()
            except DriveError as exc:
                st.warning(f"Не удалось загрузить дневник: {exc}")
                payload, file_id = {}, None
            st.session_state.meal_log = MealLog.from_dict(payload)
            st.session_state.meal_log_file_id = file_id
    return st.session_state.meal_log, client


def _save_meal_log() -> None:
    client = _get_drive_client()
    if client is None:
        st.warning("Drive не подключён — изменения дневника не сохранены в облако.")
        return
    try:
        uploaded = client.save_meal_log(st.session_state.meal_log.to_dict())
        st.session_state.meal_log_file_id = uploaded.file_id
    except DriveError as exc:
        st.error(f"Не удалось сохранить дневник: {exc}")


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def _sidebar() -> None:
    with st.sidebar:
        st.markdown("## 🍲 Recipe Vault")
        st.caption("Облачная книга рецептов")
        st.divider()

        nav_options = {
            "home": "🏠 Главная",
            "editor": "✏️ Редактор",
            "library": "📚 Библиотека",
            "diary": "📅 Дневник",
        }
        for key, label in nav_options.items():
            if st.button(label, use_container_width=True,
                         type=("primary" if st.session_state.page == key else "secondary"),
                         key=f"nav_{key}"):
                st.session_state.page = key
                st.rerun()

        st.divider()
        st.markdown("### Google Drive")
        client = _get_drive_client()
        if client is None:
            st.warning(
                "Не подключён. Заполните `.streamlit/secrets.toml` "
                "(см. `secrets.toml.example`) или Secrets в Streamlit Cloud."
            )
            with st.expander("Как подключить"):
                st.markdown(
                    "1. В Google Cloud Console создайте **Service Account** и ключ JSON.\n"
                    "2. Включите Google Drive API.\n"
                    "3. Создайте папку в Drive, расшарьте с email сервисного аккаунта (Editor).\n"
                    "4. Скопируйте `folder_id` из URL.\n"
                    "5. Вставьте в Streamlit Secrets:\n"
                    "   - `[gcp_service_account]` — поля из JSON.\n"
                    "   - `[google_drive] folder_id = \"...\"`."
                )
        else:
            st.success(f"📂 {client.folder_id[:20]}…")
            if st.button("🔄 Обновить кэш", use_container_width=True):
                _invalidate_library()
                st.session_state.meal_log = None
                st.rerun()


# ---------------------------------------------------------------------------
# Главная: плитки категорий + умный поиск
# ---------------------------------------------------------------------------

def render_home() -> None:
    st.title("🍲 Recipe Vault")
    st.caption("Загружайте, адаптируйте, считайте КБЖУ и ведите дневник питания.")

    client = _get_drive_client()
    library = _cached_library(client.folder_id if client else "")
    recipes = _recipes_from_library(library)

    # Поиск
    st.markdown("### 🔎 Поиск")
    cols = st.columns([5, 1])
    with cols[0]:
        query = st.text_input(
            "Поиск по словам",
            value=st.session_state.search_query,
            placeholder="борщ, курица карри, без мяса…",
            label_visibility="collapsed",
        )
    with cols[1]:
        only_fav = st.checkbox("⭐ Избранное", value=st.session_state.favorites_only)

    st.session_state.search_query = query
    st.session_state.favorites_only = only_fav

    if query.strip() or only_fav:
        hits = search_recipes(recipes, query, only_favorites=only_fav)
        st.markdown(f"**Найдено: {len(hits)}**")
        _render_recipes_grid([h.recipe for h in hits], context="home-search")
        if not hits:
            st.info("Ничего не нашли. Попробуйте другое слово или загрузите рецепт в редакторе.")
        return

    # Категории-плитки
    st.markdown("### 🗂 Категории")
    counts = Counter(r.get("category", "") for r in recipes)
    grid_cols = st.columns(4)
    for i, cat in enumerate(cats.load_categories()):
        col = grid_cols[i % 4]
        with col:
            count = counts.get(cat.key, 0)
            with st.container(border=True):
                st.markdown(
                    f"<div style='font-size:2.2rem;line-height:1'>{cat.emoji}</div>"
                    f"<div style='font-size:1.05rem;font-weight:600;margin-top:.2rem'>{cat.label}</div>"
                    f"<div style='color:#888;font-size:.85rem'>{count} рецеп.</div>",
                    unsafe_allow_html=True,
                )
                if st.button("Открыть", key=f"cat_{cat.key}", use_container_width=True):
                    st.session_state.selected_category = cat.key
                    st.session_state.page = "library"
                    st.rerun()

    st.divider()
    st.markdown("### 🆕 Последние добавленные")
    recent = sorted(recipes, key=lambda r: r.get("_modified", ""), reverse=True)[:6]
    if recent:
        _render_recipes_grid(recent, context="home-recent")
    else:
        st.info("Пока пусто. Откройте «Редактор» и загрузите первый рецепт.")


def _render_recipes_grid(recipes: list[dict[str, Any]], context: str) -> None:
    if not recipes:
        return
    cols = st.columns(3)
    for i, r in enumerate(recipes):
        with cols[i % 3]:
            with st.container(border=True):
                title = r.get("title") or "Без названия"
                cat = cats.label_of(r.get("category", ""))
                star = "⭐ " if r.get("favorite") else ""
                st.markdown(f"**{star}{title}**")
                st.caption(f"{cat} · {r.get('time') or '—'} · порций: {r.get('servings') or '—'}")
                tags = r.get("tags") or []
                if tags:
                    st.caption("🏷 " + ", ".join(tags[:5]))
                if st.button("Открыть", key=f"{context}_{r.get('_file_id', i)}",
                             use_container_width=True):
                    st.session_state.selected_recipe_id = r.get("_file_id", "")
                    st.session_state.page = "library"
                    st.rerun()


# ---------------------------------------------------------------------------
# Редактор: upload → adapt → save
# ---------------------------------------------------------------------------

def render_editor() -> None:
    st.title("✏️ Редактор рецепта")
    stage = st.session_state.editor_stage
    tabs_label = {"upload": "1. Загрузка", "adapt": "2. Адаптация", "save": "3. Сохранение"}
    st.markdown(" → ".join(
        f"**{v}**" if k == stage else v for k, v in tabs_label.items()
    ))
    st.divider()

    if stage == "upload":
        _render_upload()
    elif stage == "adapt":
        _render_adapt()
    elif stage == "save":
        _render_save()


def _render_upload() -> None:
    st.subheader("Загрузить файл")
    st.caption(
        "PDF, DOCX, фото/сканы (PNG/JPG/TIFF/WebP), .txt. Для рукописных и сканов — OCR (rus+eng)."
    )

    col1, col2 = st.columns([2, 1])
    with col1:
        uploaded = st.file_uploader(
            "Файл рецепта",
            type=[e.lstrip(".") for e in SUPPORTED_EXTS],
            accept_multiple_files=False,
        )
    with col2:
        force_ocr = st.checkbox("Принудительный OCR (для PDF-сканов)", value=False)
        langs = st.text_input("Языки OCR", value="rus+eng")

    if st.button("✨ Начать с пустого рецепта"):
        st.session_state.raw_text = ""
        st.session_state.load_meta = None
        st.session_state.recipe = Recipe()
        st.session_state.editor_stage = "adapt"
        st.rerun()

    if uploaded is None:
        st.info("Загрузите файл или начните с пустого рецепта.")
        return

    if st.button("Распознать и продолжить →", type="primary"):
        with st.spinner("Читаю файл…"):
            try:
                data = uploaded.read()
                result = load_file(uploaded.name, data, force_ocr=force_ocr,
                                   langs=langs.strip() or None)
            except ValueError as exc:
                st.error(str(exc))
                return
            except Exception as exc:  # pragma: no cover
                st.error(f"Не удалось обработать файл: {exc}")
                return
        st.session_state.raw_text = result.text
        st.session_state.load_meta = result
        st.session_state.last_filename = uploaded.name
        st.session_state.recipe = parse_recipe(result.text)
        st.session_state.editor_stage = "adapt"
        st.rerun()


def _render_load_summary(meta: Optional[LoadResult]) -> None:
    if meta is None:
        return
    cols = st.columns(4)
    cols[0].metric("Источник", meta.source_type)
    cols[1].metric("OCR", "да" if meta.ocr_used else "нет")
    cols[2].metric("Страниц", meta.pages or "—")
    cols[3].metric("Символов", len(meta.text))
    if meta.warnings:
        with st.expander("Предупреждения парсинга"):
            for w in meta.warnings:
                st.write(f"• {w}")


def _list_editor(label: str, items: list[str], key: str, height: int = 200) -> list[str]:
    text = st.text_area(label, value="\n".join(items), key=key, height=height,
                        help="Каждый элемент с новой строки.")
    return [line.strip() for line in text.split("\n") if line.strip()]


def _render_adapt() -> None:
    st.subheader("Редактировать структуру")
    _render_load_summary(st.session_state.load_meta)
    recipe: Recipe = st.session_state.recipe

    left, right = st.columns([1, 1])
    with left:
        st.markdown("**Сырой распознанный текст** (правьте артефакты)")
        new_raw = st.text_area("raw", value=st.session_state.raw_text, height=460,
                               label_visibility="collapsed")
        sub = st.columns(2)
        if sub[0].button("🔁 Перепарсить из текста"):
            st.session_state.raw_text = new_raw
            parsed = parse_recipe(new_raw)
            # сохраняем категорию/теги/избранное, если уже выставлены
            parsed.category = recipe.category
            parsed.tags = recipe.tags
            parsed.favorite = recipe.favorite
            parsed.cuisine = recipe.cuisine
            parsed.difficulty = recipe.difficulty
            st.session_state.recipe = parsed
            st.rerun()
        if sub[1].button("↩ Сбросить структуру"):
            st.session_state.recipe = parse_recipe(st.session_state.raw_text)
            st.rerun()
        st.session_state.raw_text = new_raw

    with right:
        recipe.title = st.text_input("Название", value=recipe.title)

        cat_options = [("", "— без категории —")] + cats.options_for_select()
        cur_idx = next((i for i, (k, _) in enumerate(cat_options) if k == recipe.category), 0)
        chosen = st.selectbox("Категория", options=cat_options, index=cur_idx,
                              format_func=lambda x: x[1])
        recipe.category = chosen[0]

        meta_cols = st.columns(3)
        recipe.servings = meta_cols[0].text_input("Порций", value=recipe.servings)
        recipe.time = meta_cols[1].text_input("Время", value=recipe.time)
        recipe.difficulty = meta_cols[2].selectbox(
            "Сложность",
            options=["", "легко", "средне", "сложно"],
            index=["", "легко", "средне", "сложно"].index(recipe.difficulty or ""),
        )

        cuisine_fav = st.columns([3, 1])
        recipe.cuisine = cuisine_fav[0].text_input(
            "Кухня", value=recipe.cuisine,
            placeholder="русская / итальянская / азиатская…",
        )
        recipe.favorite = cuisine_fav[1].checkbox("⭐", value=recipe.favorite)

        tags_text = st.text_input(
            "Теги (через запятую)",
            value=", ".join(recipe.tags),
            placeholder="быстро, постное, на выходные",
        )
        recipe.tags = [t.strip() for t in tags_text.split(",") if t.strip()]

        recipe.ingredients = _list_editor("Ингредиенты", recipe.ingredients,
                                          key="ingredients_edit", height=190)
        recipe.steps = _list_editor("Шаги приготовления", recipe.steps,
                                    key="steps_edit", height=220)
        recipe.notes = st.text_area("Заметки", value=recipe.notes, height=80)
        st.session_state.recipe = recipe

    st.divider()
    st.markdown("**Предпросмотр**")
    st.markdown(st.session_state.recipe.to_markdown())

    nav = st.columns([1, 1, 4])
    if nav[0].button("← К загрузке"):
        st.session_state.editor_stage = "upload"
        st.rerun()
    if nav[1].button("Сохранить →", type="primary"):
        st.session_state.editor_stage = "save"
        st.rerun()


def _render_save() -> None:
    st.subheader("Сохранить в Google Drive")
    recipe: Recipe = st.session_state.recipe
    md = recipe.to_markdown()
    if not recipe.title.strip():
        st.warning("Без названия не сохранить — вернитесь на шаг адаптации.")

    payload = {
        "saved_at": datetime.utcnow().isoformat() + "Z",
        "source_filename": st.session_state.last_filename,
        "recipe": recipe.to_dict(),
    }

    preview = st.columns([1, 1])
    with preview[0]:
        st.markdown("**Markdown → Google Doc**")
        st.code(md, language="markdown")
    with preview[1]:
        st.markdown("**JSON-бэкап**")
        st.code(json.dumps(payload, ensure_ascii=False, indent=2), language="json")

    client = _get_drive_client()
    opt = st.columns(3)
    save_doc = opt[0].checkbox("Google Doc", value=True)
    save_md = opt[1].checkbox("Markdown файл (.md)", value=False)
    save_json = opt[2].checkbox("JSON-бэкап (.json)", value=True,
                                help="Нужен для библиотеки и поиска.")

    nav = st.columns([1, 1, 2])
    if nav[0].button("← Назад"):
        st.session_state.editor_stage = "adapt"
        st.rerun()
    name = (recipe.title.strip() or "recipe").replace("/", "_")
    nav[1].download_button("⬇ .md", data=md.encode("utf-8"),
                           file_name=f"{name}.md", mime="text/markdown")
    if nav[2].button("☁️ Сохранить в Drive", type="primary", disabled=(client is None)):
        if client is None:
            st.error("Drive не подключён.")
            return
        results = []
        with st.spinner("Загружаю…"):
            try:
                if save_doc:
                    results.append(client.save_markdown_as_doc(recipe.title, md))
                if save_md:
                    results.append(client.save_markdown_file(recipe.title, md))
                if save_json:
                    results.append(client.save_json_backup(recipe.title, payload))
            except DriveError as exc:
                st.error(f"Drive: {exc}")
                return
        st.success(f"Сохранено: {len(results)} файлов")
        for f in results:
            st.markdown(f"• [{f.name}]({f.web_link}) `{f.mime_type.rsplit('.', 1)[-1]}`")
            st.session_state.saved_links.append(
                {"name": f.name, "link": f.web_link, "mime": f.mime_type}
            )
        _invalidate_library()


# ---------------------------------------------------------------------------
# Библиотека + панель рецепта с КБЖУ
# ---------------------------------------------------------------------------

def render_library() -> None:
    st.title("📚 Библиотека рецептов")
    client = _get_drive_client()
    library = _cached_library(client.folder_id if client else "")
    recipes = _recipes_from_library(library)

    if client is None:
        st.info("Подключите Google Drive в сайдбаре, чтобы загрузить рецепты.")
        return
    if not recipes:
        st.info("В папке Drive пока нет JSON-бэкапов рецептов. "
                "Сохраните рецепт через редактор с галочкой «JSON-бэкап».")
        return

    # Фильтры
    flt = st.columns([2, 2, 2, 1])
    with flt[0]:
        query = st.text_input("Поиск", value=st.session_state.search_query,
                              placeholder="борщ, без мяса, постное…")
        st.session_state.search_query = query
    with flt[1]:
        cat_options = [("", "Все категории")] + cats.options_for_select()
        cur_idx = next((i for i, (k, _) in enumerate(cat_options)
                        if k == st.session_state.selected_category), 0)
        chosen = st.selectbox("Категория", options=cat_options, index=cur_idx,
                              format_func=lambda x: x[1])
        st.session_state.selected_category = chosen[0]
    with flt[2]:
        all_tags = sorted({t for r in recipes for t in (r.get("tags") or [])})
        chosen_tags = st.multiselect("Теги", options=all_tags)
    with flt[3]:
        only_fav = st.checkbox("⭐ Избр.", value=st.session_state.favorites_only)
        st.session_state.favorites_only = only_fav

    hits = search_recipes(recipes, query,
                          category=st.session_state.selected_category or None,
                          only_favorites=only_fav)
    if chosen_tags:
        hits = [h for h in hits if set(chosen_tags) & set(h.recipe.get("tags") or [])]

    st.caption(f"Показано: {len(hits)} из {len(recipes)}")

    # Если выбран рецепт — показываем детальную панель
    if st.session_state.selected_recipe_id:
        selected = next((r for r in recipes
                         if r.get("_file_id") == st.session_state.selected_recipe_id), None)
        if selected:
            _render_recipe_detail(selected)
            st.divider()

    # Список рецептов
    if not hits:
        st.info("По фильтрам ничего нет.")
        return
    for h in hits:
        r = h.recipe
        with st.container(border=True):
            top = st.columns([5, 2, 2, 1])
            star = "⭐ " if r.get("favorite") else ""
            top[0].markdown(f"**{star}{r.get('title') or 'Без названия'}**")
            top[1].caption(cats.label_of(r.get("category", "")))
            top[2].caption(f"⏱ {r.get('time') or '—'} · 🍽 {r.get('servings') or '—'}")
            if top[3].button("Открыть", key=f"lib_open_{r['_file_id']}"):
                st.session_state.selected_recipe_id = r["_file_id"]
                st.rerun()
            tags = r.get("tags") or []
            if tags:
                st.caption("🏷 " + ", ".join(tags))


def _render_nutrition_block(n: Nutrition, title: str) -> None:
    n = n.round()
    cols = st.columns(4)
    cols[0].metric("Ккал", f"{n.kcal:.0f}")
    cols[1].metric("Б", f"{n.protein:.1f} г")
    cols[2].metric("Ж", f"{n.fat:.1f} г")
    cols[3].metric("У", f"{n.carbs:.1f} г")


def _render_recipe_detail(r: dict[str, Any]) -> None:
    title = r.get("title") or "Без названия"
    st.markdown(f"## {title}")
    meta = []
    if r.get("category"):
        meta.append(cats.label_of(r["category"]))
    if r.get("cuisine"):
        meta.append(f"🌍 {r['cuisine']}")
    if r.get("time"):
        meta.append(f"⏱ {r['time']}")
    if r.get("servings"):
        meta.append(f"🍽 порций: {r['servings']}")
    if r.get("difficulty"):
        meta.append(f"💪 {r['difficulty']}")
    if r.get("favorite"):
        meta.append("⭐")
    if meta:
        st.caption(" · ".join(meta))
    if r.get("tags"):
        st.caption("🏷 " + ", ".join(r["tags"]))

    tabs = st.tabs(["📖 Рецепт", "🔥 КБЖУ", "📅 В дневник"])

    with tabs[0]:
        if r.get("ingredients"):
            st.markdown("**Ингредиенты**")
            for i in r["ingredients"]:
                st.markdown(f"- {i}")
        if r.get("steps"):
            st.markdown("**Приготовление**")
            for i, s in enumerate(r["steps"], 1):
                st.markdown(f"{i}. {s}")
        if r.get("notes"):
            st.markdown("**Заметки**")
            st.markdown(r["notes"])
        actions = st.columns(3)
        if actions[0].button("✏️ Открыть в редакторе", key=f"edit_{r['_file_id']}"):
            st.session_state.recipe = Recipe.from_dict(r)
            st.session_state.raw_text = r.get("raw_text") or st.session_state.recipe.to_markdown()
            st.session_state.last_filename = r.get("_file_name", "")
            st.session_state.editor_stage = "adapt"
            st.session_state.page = "editor"
            st.rerun()
        if actions[1].button("✖ Закрыть", key=f"close_{r['_file_id']}"):
            st.session_state.selected_recipe_id = ""
            st.rerun()
        if r.get("_web_link"):
            actions[2].markdown(f"[🔗 Открыть в Drive]({r['_web_link']})")

    with tabs[1]:
        _render_nutrition_panel(r)

    with tabs[2]:
        _render_log_form(r)


def _render_nutrition_panel(r: dict[str, Any]) -> None:
    st.markdown("### 🔥 Расчёт КБЖУ")
    base_servings = parse_servings(r.get("servings", ""))
    cols = st.columns([1, 1, 2])
    new_servings = cols[0].number_input(
        "Порций", min_value=0.5, max_value=50.0,
        value=float(base_servings or 1.0), step=0.5,
        key=f"nut_servings_{r['_file_id']}",
    )
    scaler = cols[1].number_input(
        "Масштаб ингредиентов", min_value=0.1, max_value=10.0,
        value=1.0, step=0.5,
        help="Все количества умножатся на этот коэффициент.",
        key=f"nut_scaler_{r['_file_id']}",
    )

    ingredients = r.get("ingredients") or []
    if not ingredients:
        st.info("В рецепте нет ингредиентов для расчёта.")
        return

    # Грязный путь масштабирования: если scaler != 1, мы пересчитываем граммы пропорционально.
    rn = calc_recipe(ingredients, servings=new_servings, products=load_products())
    if scaler != 1.0:
        # масштабируем итоговое
        rn.total = rn.total.scale(scaler)
        rn.total_grams *= scaler
        for item in rn.items:
            if item.grams:
                item.grams *= scaler
            item.nutrition = item.nutrition.scale(scaler)

    st.markdown("**На весь рецепт**")
    _render_nutrition_block(rn.total, "всего")
    st.markdown(f"**На порцию** (из {new_servings:g})")
    _render_nutrition_block(rn.per_serving, "порция")
    if rn.total_grams:
        st.caption(f"Общий вес: {rn.total_grams:.0f} г · на 100 г: "
                   f"{rn.per_100g.kcal:.0f} ккал / "
                   f"Б {rn.per_100g.protein:.1f} / "
                   f"Ж {rn.per_100g.fat:.1f} / "
                   f"У {rn.per_100g.carbs:.1f}")

    with st.expander("📋 Детализация по ингредиентам"):
        rows = []
        warnings = []
        for item in rn.items:
            n = item.nutrition.round()
            rows.append({
                "Ингредиент": item.parsed.raw,
                "В БД": item.product_name or "—",
                "Граммов": f"{item.grams:.0f}" if item.grams else "—",
                "Ккал": f"{n.kcal:.0f}",
                "Б": f"{n.protein:.1f}",
                "Ж": f"{n.fat:.1f}",
                "У": f"{n.carbs:.1f}",
                "Совпадение": f"{item.match_score:.0%}" if item.match_score else "—",
            })
            if item.warning:
                warnings.append(f"• {item.parsed.raw}: {item.warning}")
        st.dataframe(rows, use_container_width=True, hide_index=True)
        if warnings:
            st.caption("⚠️ Не учтены полностью:")
            for w in warnings:
                st.caption(w)
        st.caption(
            "БД содержит ~100 базовых продуктов (`data/nutrition_ru.csv`). "
            "Расширяйте её — точность вырастет."
        )


def _render_log_form(r: dict[str, Any]) -> None:
    st.markdown("### 📅 Записать в дневник")
    cols = st.columns([1, 1, 1, 1])
    with cols[0]:
        d = st.date_input("Дата", value=st.session_state.diary_date,
                          key=f"log_date_{r['_file_id']}")
    with cols[1]:
        meal_type = st.selectbox("Приём пищи", MEAL_TYPES,
                                 index=MEAL_TYPES.index(st.session_state.diary_meal_type),
                                 key=f"log_type_{r['_file_id']}")
    with cols[2]:
        portions = st.number_input(
            "Порций", min_value=0.1, max_value=20.0,
            value=1.0, step=0.5,
            key=f"log_portions_{r['_file_id']}",
        )
    with cols[3]:
        st.write("")
        st.write("")
        if st.button("➕ Добавить", type="primary", key=f"log_add_{r['_file_id']}"):
            base_servings = parse_servings(r.get("servings", ""))
            rn = calc_recipe(r.get("ingredients") or [],
                             servings=base_servings, products=load_products())
            per_entry = rn.per_serving.scale(portions).round()
            log, _ = _ensure_meal_log()
            entry = MealEntry(
                id="",
                date=d.isoformat(),
                meal_type=meal_type,
                recipe_title=r.get("title") or "Без названия",
                recipe_file_id=r.get("_file_id", ""),
                portions=portions,
                nutrition=per_entry.to_dict(),
            )
            log.add(entry)
            _save_meal_log()
            st.session_state.diary_date = d
            st.session_state.diary_meal_type = meal_type
            st.success(f"Добавлено в дневник: {d.isoformat()} — {meal_type}, "
                       f"{per_entry.kcal:.0f} ккал × {portions}")
    notes = st.text_input("Заметка", placeholder="Например, заменил масло на оливковое",
                          key=f"log_notes_{r['_file_id']}")
    if notes:
        # сохраняем в session state, но привязать к новому entry в этой логике некуда —
        # либо переход к более сложному UI, либо edit entry в диары. Оставим для будущего.
        st.caption("Заметку можно отредактировать у созданной записи на странице «Дневник».")


# ---------------------------------------------------------------------------
# Дневник
# ---------------------------------------------------------------------------

def render_diary() -> None:
    st.title("📅 Дневник питания")
    log, client = _ensure_meal_log()

    if client is None:
        st.warning("Drive не подключён — дневник работает только в текущей сессии "
                   "и не сохраняется в облако.")

    st.markdown("### Что вы хотите/ели сегодня?")
    cols = st.columns([1, 1, 4])
    with cols[0]:
        d = st.date_input("Дата", value=st.session_state.diary_date)
        st.session_state.diary_date = d
    with cols[1]:
        if st.button("🔄 Перезагрузить из Drive", use_container_width=True):
            st.session_state.meal_log = None
            st.rerun()
    with cols[2]:
        nav = st.columns([1, 1, 1])
        if nav[0].button("📚 К библиотеке →"):
            st.session_state.page = "library"
            st.rerun()

    # Сводка дня
    totals = log.daily_totals(d)
    st.markdown(f"**Сводка за {d.isoformat()}**")
    sum_cols = st.columns(4)
    sum_cols[0].metric("Ккал", f"{totals['kcal']:.0f}")
    sum_cols[1].metric("Белки", f"{totals['protein']:.1f} г")
    sum_cols[2].metric("Жиры", f"{totals['fat']:.1f} г")
    sum_cols[3].metric("Углеводы", f"{totals['carbs']:.1f} г")

    entries = sorted(log.for_date(d),
                     key=lambda e: MEAL_TYPES.index(e.meal_type)
                     if e.meal_type in MEAL_TYPES else 99)
    if not entries:
        st.info("На эту дату записей нет. Откройте рецепт в библиотеке и нажмите "
                "«➕ Добавить» во вкладке «В дневник».")
    else:
        for e in entries:
            with st.container(border=True):
                top = st.columns([3, 1, 1, 1, 1, 1])
                top[0].markdown(f"**{e.meal_type.capitalize()}** · {e.recipe_title}")
                top[1].caption(f"× {e.portions:g} порц.")
                top[2].caption(f"🔥 {float(e.nutrition.get('kcal', 0)):.0f} ккал")
                top[3].caption(f"Б {float(e.nutrition.get('protein', 0)):.1f}")
                top[4].caption(f"Ж {float(e.nutrition.get('fat', 0)):.1f}")
                top[5].caption(f"У {float(e.nutrition.get('carbs', 0)):.1f}")
                if e.notes:
                    st.caption(f"📝 {e.notes}")
                actions = st.columns([1, 1, 4])
                new_notes = actions[0].text_input("Заметка", value=e.notes,
                                                  key=f"diary_note_{e.id}",
                                                  label_visibility="collapsed",
                                                  placeholder="заметка")
                if actions[1].button("💾", key=f"diary_save_{e.id}",
                                     help="Сохранить заметку"):
                    e.notes = new_notes
                    log.update(e)
                    _save_meal_log()
                    st.rerun()
                if actions[2].button("🗑 Удалить", key=f"diary_del_{e.id}"):
                    log.remove(e.id)
                    _save_meal_log()
                    st.rerun()

    st.divider()
    st.markdown("### 📈 За последние 7 дней")
    from datetime import timedelta
    start = d - timedelta(days=6)
    rng = log.range(start, d)
    if not rng:
        st.caption("Нет данных за последнюю неделю.")
    else:
        by_day: dict[str, dict[str, float]] = {}
        for e in rng:
            agg = by_day.setdefault(e.date, {"kcal": 0, "protein": 0, "fat": 0, "carbs": 0})
            for k in agg:
                agg[k] += float(e.nutrition.get(k, 0))
        rows = [{"Дата": dt, "Ккал": round(v["kcal"]),
                 "Б": round(v["protein"], 1), "Ж": round(v["fat"], 1),
                 "У": round(v["carbs"], 1)}
                for dt, v in sorted(by_day.items())]
        st.dataframe(rows, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------

def main() -> None:
    _sidebar()
    page = st.session_state.page
    if page == "home":
        render_home()
    elif page == "editor":
        render_editor()
    elif page == "library":
        render_library()
    elif page == "diary":
        render_diary()
    else:
        render_home()


if __name__ == "__main__":
    main()
