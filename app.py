"""Recipe Vault — Streamlit-приложение для оцифровки и хранения рецептов.

Страницы:
- Главная: плитки категорий + умный поиск.
- Редактор: загрузка (PDF/DOCX/фото с OCR) → адаптация → сохранение в Google Drive.
- Библиотека: список рецептов из папки Drive с фильтрами и панелью КБЖУ.
- Холодильник: продукты с весами + подбор рецептов под имеющиеся продукты.
- Дневник: «Что вы хотите сегодня?» — лог съеденного с расчётом КБЖУ за день.
- О разработке: 4-вкладочная витрина продукта.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime
from typing import Any, Optional

import streamlit as st

from src import categories as cats
from src.about_ui import render_about
from src.file_loader import LoadResult, SUPPORTED_EXTS, load_file
from src.google_drive import DriveClient, DriveError
from src.meal_log import MEAL_TYPES, MealEntry, MealLog
from src.nutrition import (Nutrition, calc_recipe, load_products, parse_servings)
from src.pantry import Pantry, PantryItem, parse_user_input
from src.recipe_matcher import suggest as suggest_recipes
from src.recipe_parser import Recipe, parse_recipe
from src.search import search as search_recipes
from src.theme import hair, inject_theme, page_header, section_h


st.set_page_config(
    page_title="Recipe Vault",
    page_icon="🍲",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_theme()


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
        "pantry": None,
        "pantry_file_id": None,
        "pantry_input": "",
        "pantry_suggestions": None,
        "pantry_selected_recipe": None,
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


def _ensure_pantry() -> tuple[Pantry, DriveClient | None]:
    client = _get_drive_client()
    if st.session_state.pantry is None:
        if client is None:
            st.session_state.pantry = Pantry()
        else:
            try:
                payload, file_id = client.load_pantry()
            except DriveError as exc:
                st.warning(f"Не удалось загрузить холодильник: {exc}")
                payload, file_id = {}, None
            st.session_state.pantry = Pantry.from_dict(payload)
            st.session_state.pantry_file_id = file_id
    return st.session_state.pantry, client


def _save_pantry() -> None:
    client = _get_drive_client()
    if client is None:
        st.warning("Drive не подключён — холодильник сохранён только в этой сессии.")
        return
    try:
        uploaded = client.save_pantry(st.session_state.pantry.to_dict())
        st.session_state.pantry_file_id = uploaded.file_id
    except DriveError as exc:
        st.error(f"Не удалось сохранить холодильник: {exc}")


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def _sidebar() -> None:
    with st.sidebar:
        st.markdown(
            '<div style="font-family:var(--rv-sans);font-size:1.25rem;'
            'font-weight:700;color:var(--rv-ink);letter-spacing:-.01em;">'
            'recipe vault</div>'
            '<div style="color:var(--rv-ink-mute);font-size:.82rem;'
            'margin-top:.15rem;">облачная книга рецептов</div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="rv-hair"></div>', unsafe_allow_html=True)

        nav_options = {
            "home": "главная",
            "editor": "редактор",
            "library": "библиотека",
            "pantry": "холодильник",
            "diary": "дневник",
            "about": "о разработке",
        }
        for key, label in nav_options.items():
            if st.button(label, use_container_width=True,
                         type=("primary" if st.session_state.page == key else "secondary"),
                         key=f"nav_{key}"):
                st.session_state.page = key
                st.rerun()

        st.markdown('<div class="rv-hair"></div>', unsafe_allow_html=True)
        st.markdown('<div class="rv-h-eyebrow">google drive</div>',
                    unsafe_allow_html=True)
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
                st.session_state.pantry = None
                st.rerun()


# ---------------------------------------------------------------------------
# Главная: плитки категорий + умный поиск
# ---------------------------------------------------------------------------

def render_home() -> None:
    page_header(
        eyebrow="recipe vault · облачная книга рецептов",
        title="главная",
        lead="Оцифровать бумажные листочки. Посчитать КБЖУ без догадок. "
             "Приготовить из того, что лежит в холодильнике. "
             "Записать, что съели сегодня. Всё — в одной папке Google Drive.",
    )

    client = _get_drive_client()
    library = _cached_library(client.folder_id if client else "")
    recipes = _recipes_from_library(library)

    # ── Поиск ────────────────────────────────────────────────────────────────
    section_h("01", "Поиск")
    cols = st.columns([5, 1])
    with cols[0]:
        query = st.text_input(
            "Поиск по словам",
            value=st.session_state.search_query,
            placeholder="борщ, курица карри, без мяса…",
            label_visibility="collapsed",
        )
    with cols[1]:
        only_fav = st.checkbox("Только избранное", value=st.session_state.favorites_only)

    st.session_state.search_query = query
    st.session_state.favorites_only = only_fav

    if query.strip() or only_fav:
        hits = search_recipes(recipes, query, only_favorites=only_fav)
        st.markdown(
            f'<div class="rv-caption">Найдено: {len(hits)}</div>',
            unsafe_allow_html=True,
        )
        _render_recipes_grid([h.recipe for h in hits], context="home-search")
        if not hits:
            st.info("Ничего не нашли. Попробуйте другое слово или загрузите рецепт в редакторе.")
        return

    # ── Категории ────────────────────────────────────────────────────────────
    hair()
    section_h("02", "категории")
    counts = Counter(r.get("category", "") for r in recipes)
    grid_cols = st.columns(4)
    for i, cat in enumerate(cats.load_categories()):
        col = grid_cols[i % 4]
        count = counts.get(cat.key, 0)
        with col:
            st.markdown(
                '<div style="margin-bottom:14px;">'
                f'<div class="rv-photo-zone">{cat.emoji}</div>'
                f'<div style="display:flex;justify-content:space-between;'
                f'align-items:baseline;font-size:.95rem;">'
                f'  <span style="font-weight:600;color:var(--rv-ink);">{cat.label.lower()}</span>'
                f'  <span style="color:var(--rv-ink-mute);font-size:.82rem;">{count:02d}</span>'
                f'</div>'
                '</div>',
                unsafe_allow_html=True,
            )
            if st.button("открыть", key=f"cat_{cat.key}", use_container_width=True):
                st.session_state.selected_category = cat.key
                st.session_state.page = "library"
                st.rerun()

    # ── Последние ────────────────────────────────────────────────────────────
    hair()
    section_h("03", "Последние добавленные")
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
            title = (r.get("title") or "Без названия").lower().replace("<", "&lt;")
            cat = next((c for c in cats.load_categories()
                        if c.key == r.get("category", "")), None)
            zone_glyph = cat.emoji if cat else "·"
            star = '<span style="color:var(--rv-ink);">●</span> ' if r.get("favorite") else ""
            tags = r.get("tags") or []
            pills = "".join(f'<span class="rv-pill">{t}</span>' for t in tags[:3])
            meta_bits = []
            if r.get("time"):
                meta_bits.append(r["time"])
            if r.get("servings"):
                meta_bits.append(f"{r['servings']} порц.")
            meta = " · ".join(meta_bits) or "—"
            cat_label = cat.label.lower() if cat else "—"
            st.markdown(
                '<div style="margin-bottom:14px;">'
                f'<div class="rv-photo-zone">{zone_glyph}</div>'
                f'<div style="display:flex;justify-content:space-between;'
                f'align-items:baseline;margin-bottom:.2rem;">'
                f'  <span style="font-weight:600;color:var(--rv-ink);'
                f'font-size:1rem;">{star}{title}</span>'
                f'  <span style="color:var(--rv-ink-mute);font-size:.8rem;">{cat_label}</span>'
                f'</div>'
                f'<div style="color:var(--rv-ink-mute);font-size:.82rem;'
                f'margin-bottom:.4rem;">{meta}</div>'
                f'<div>{pills}</div>'
                '</div>',
                unsafe_allow_html=True,
            )
            if st.button("открыть", key=f"{context}_{r.get('_file_id', i)}",
                         use_container_width=True):
                st.session_state.selected_recipe_id = r.get("_file_id", "")
                st.session_state.page = "library"
                st.rerun()


# ---------------------------------------------------------------------------
# Редактор: upload → adapt → save
# ---------------------------------------------------------------------------

def render_editor() -> None:
    page_header(
        eyebrow="редактор",
        title="новый рецепт",
        lead="Три шага: загрузить файл, поправить распознанный текст и структуру, "
             "сохранить в свою папку Google Drive.",
    )
    stage = st.session_state.editor_stage
    steps = [("upload", "Загрузка"), ("adapt", "Адаптация"), ("save", "Сохранение")]
    chips = []
    for key, label in steps:
        active = key == stage
        chips.append(
            f'<span class="rv-pill {"accent" if active else ""}" '
            f'style="font-size:.72rem;{"font-weight:600;" if active else ""}">'
            f'{label}</span>'
        )
    st.markdown(
        f'<div style="margin-bottom:1.2rem;">{" → ".join(chips)}</div>',
        unsafe_allow_html=True,
    )

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
    page_header(
        eyebrow="библиотека",
        title="все рецепты",
        lead="Фильтруйте по категории, тегам и избранному. Откройте карточку — "
             "увидите расчёт КБЖУ и сможете отправить блюдо в дневник.",
    )
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
    page_header(
        eyebrow="дневник",
        title="что вы хотите сегодня?",
        lead="Выберите дату, добавьте блюдо из библиотеки с количеством порций — "
             "увидите дневной свод по калориям и БЖУ, а также таблицу за неделю.",
    )
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
# Холодильник
# ---------------------------------------------------------------------------

def render_pantry() -> None:
    page_header(
        eyebrow="холодильник",
        title="что есть — что приготовить",
        lead="Введите продукты с весами, OCR-нте список или прочитайте фото весов. "
             "Нажмите «Сгенерировать» — получите подбор рецептов с разбивкой "
             "что есть и что докупить.",
    )
    pantry, client = _ensure_pantry()
    if client is None:
        st.warning("Drive не подключён — холодильник работает только в этой сессии.")

    tabs = st.tabs([
        "текст",
        "фото-список (ocr)",
        "фото холодильника (ai)",
        "фото весов (ocr)",
        "что есть",
        "что приготовить",
    ])

    # --- 1. Текстовый ввод ---------------------------------------------------
    with tabs[0]:
        st.markdown(
            "**Каждый продукт с новой строки.** Примеры: "
            "`перец сладкий 350 г`, `2 огурца`, `молоко 2.5% 1 л`, `курица филе 500 г`."
        )
        text = st.text_area(
            "Список продуктов",
            value=st.session_state.pantry_input,
            height=180,
            label_visibility="collapsed",
        )
        st.session_state.pantry_input = text
        cols = st.columns([1, 1, 2])
        if cols[0].button("➕ Добавить в холодильник", type="primary"):
            items = parse_user_input(text)
            if not items:
                st.error("Не удалось распарсить ни одной строки.")
            else:
                for it in items:
                    pantry.add(it)
                _save_pantry()
                st.success(f"Добавлено: {len(items)}. См. вкладку «Что есть».")
                st.session_state.pantry_input = ""
                st.session_state.pantry_suggestions = None
                st.rerun()
        if cols[1].button("🔍 Проверить парсинг (без сохранения)"):
            items = parse_user_input(text)
            rows = [{"Введено": it.raw, "Распознано": it.product_name or "—",
                     "Граммы": f"{it.grams:.0f}"} for it in items]
            st.dataframe(rows, use_container_width=True, hide_index=True)

    # --- 2. Фото-список (OCR) -----------------------------------------------
    with tabs[1]:
        st.markdown(
            "Фото или скан списка продуктов. OCR (rus + eng) превратит в текст — "
            "проверьте в редактируемом поле и подтвердите."
        )
        uploaded = st.file_uploader(
            "Фото списка",
            type=[e.lstrip(".") for e in (".png", ".jpg", ".jpeg", ".webp", ".tiff", ".pdf")],
            key="pantry_ocr_list",
        )
        if uploaded is not None and st.button("🔎 Распознать"):
            try:
                data = uploaded.read()
                result = load_file(uploaded.name, data, force_ocr=True)
                st.session_state.pantry_input = result.text or ""
                st.success("Распознано. Перейдите на вкладку «Текстовый ввод» — "
                           "поправьте артефакты и нажмите «Добавить».")
                st.session_state.page = "pantry"
                st.rerun()
            except Exception as exc:  # pragma: no cover
                st.error(f"OCR не удался: {exc}")

    # --- 3. Фото холодильника (Vision / AI) ----------------------------------
    with tabs[2]:
        _render_vision_pantry_tab(pantry)

    # --- 4. Фото весов -------------------------------------------------------
    with tabs[3]:
        st.markdown(
            "Фото электронных весов с продуктом. OCR извлечёт число и единицу — "
            "вы укажете название продукта и нажмёте «Добавить»."
        )
        scale_photo = st.file_uploader(
            "Фото весов",
            type=["png", "jpg", "jpeg", "webp", "tiff"],
            key="pantry_scale_photo",
        )
        scale_cols = st.columns([2, 1])
        product_name = scale_cols[0].text_input(
            "Название продукта", placeholder="например: болгарский перец",
        )
        if scale_photo is not None and scale_cols[1].button("📏 Прочитать вес"):
            try:
                data = scale_photo.read()
                result = load_file(scale_photo.name, data, force_ocr=True)
                st.text_area("Распознано с фото", value=result.text, height=80,
                             key="scale_ocr_preview")
                st.info("Скопируйте вес в поле ниже и добавьте.")
            except Exception as exc:  # pragma: no cover
                st.error(f"OCR не удался: {exc}")
        weight_grams = st.number_input(
            "Вес (граммы)", min_value=0.0, max_value=20000.0, value=0.0, step=10.0,
        )
        if st.button("➕ Добавить продукт с весов"):
            if not product_name.strip() or weight_grams <= 0:
                st.error("Введите название и вес > 0.")
            else:
                from src.nutrition import find_product
                match = find_product(product_name)
                canonical = match[0].name if match else ""
                pantry.add(PantryItem(
                    id="", raw=f"{product_name} {weight_grams:.0f} г",
                    name=product_name, product_name=canonical,
                    grams=float(weight_grams),
                ))
                _save_pantry()
                st.success(f"Добавлено: {product_name} — {weight_grams:.0f} г. "
                           f"Сопоставлено с «{canonical or '— не найдено в БД —'}».")
                st.rerun()

    # --- 5. Что есть ---------------------------------------------------------
    with tabs[4]:
        if not pantry.items:
            st.info("Холодильник пуст. Добавьте продукты на других вкладках.")
        else:
            sum_g = sum(it.grams for it in pantry.items)
            unmatched_n = sum(1 for it in pantry.items if not it.product_name)
            mcols = st.columns(3)
            mcols[0].metric("Позиций", len(pantry.items))
            mcols[1].metric("Всего, г", f"{sum_g:.0f}")
            mcols[2].metric("Не в БД", unmatched_n,
                            help="Эти продукты не участвуют в матчинге рецептов.")
            for it in pantry.items:
                with st.container(border=True):
                    cols = st.columns([4, 2, 2, 1])
                    cols[0].markdown(f"**{it.name or it.raw}**")
                    cols[0].caption(it.raw)
                    matched_label = it.product_name or "— не найден в БД —"
                    cols[1].caption(f"🔗 {matched_label}")
                    new_g = cols[2].number_input(
                        "г", min_value=0.0, max_value=50000.0,
                        value=float(it.grams), step=10.0,
                        key=f"pantry_g_{it.id}", label_visibility="collapsed",
                    )
                    if new_g != it.grams:
                        it.grams = new_g
                        pantry.update(it)
                        _save_pantry()
                    if cols[3].button("🗑", key=f"pantry_del_{it.id}"):
                        pantry.remove(it.id)
                        _save_pantry()
                        st.rerun()
            if st.button("🧹 Очистить холодильник"):
                pantry.clear()
                _save_pantry()
                st.rerun()

    # --- 6. Что приготовить --------------------------------------------------
    with tabs[5]:
        st.markdown("**Сгенерировать рецепты** из того, что лежит в холодильнике.")
        cols = st.columns([1, 1, 1])
        include_starter = cols[0].checkbox(
            "+ стартовый набор рецептов", value=True,
            help="20 базовых блюд в `data/starter_recipes.json`",
        )
        min_cov_pct = cols[1].slider("Мин. покрытие, %", 0, 100, 20, step=5)
        top_n = cols[2].slider("Сколько показать", 3, 30, 10)

        if st.button("✨ Сгенерировать", type="primary", disabled=not pantry.items):
            client_ = _get_drive_client()
            lib = _cached_library(client_.folder_id if client_ else "")
            user_recipes = _recipes_from_library(lib)
            grams = pantry.grams_by_product()
            matches = suggest_recipes(
                grams,
                user_recipes=user_recipes,
                include_starter=include_starter,
                top_n=top_n,
                min_coverage=min_cov_pct / 100.0,
            )
            st.session_state.pantry_suggestions = matches

        suggestions = st.session_state.pantry_suggestions
        if not pantry.items:
            st.info("Сначала добавьте продукты на других вкладках.")
        elif suggestions is None:
            st.info("Нажмите «Сгенерировать», чтобы получить подборку.")
        elif not suggestions:
            st.warning("Под текущие фильтры ничего не нашлось. Снизьте минимальное "
                       "покрытие или добавьте больше продуктов.")
        else:
            for m in suggestions:
                _render_match_card(m)


def _render_vision_pantry_tab(pantry: Pantry) -> None:
    """Vкладка «фото холодильника (ai)» — распознавание продуктов через Claude Vision."""
    from src.vision import (DEFAULT_MODEL, VisionUnavailable,
                            describe_fridge_photo, has_api_key)

    st.markdown(
        "Загрузите фото холодильника или продуктов на столе. "
        "Claude Vision определит продукты и оценит вес каждого. "
        "Никаких «йогурт в борщ» — модель различает сладкие/несладкие категории."
    )

    if not has_api_key():
        st.info(
            "🔑 Нужен Anthropic API-ключ. Что сделать:\n\n"
            "1. Завести аккаунт на https://console.anthropic.com\n"
            "2. Выпустить API-ключ (раздел **API Keys**).\n"
            "3. В Streamlit Cloud → Settings → Secrets добавить строку:\n"
            "   ```\n"
            '   ANTHROPIC_API_KEY = "sk-ant-..."\n'
            "   ```\n"
            "4. Сохранить → приложение перезапустится автоматически.\n\n"
            "Стоимость распознавания фото — около **$0.005** (Haiku 4.5)."
        )

    photo = st.file_uploader(
        "Фото холодильника / продуктов",
        type=["png", "jpg", "jpeg", "webp"],
        key="pantry_vision_photo",
    )
    cols = st.columns([2, 1, 1])
    model = cols[0].selectbox(
        "Модель",
        options=[
            "claude-haiku-4-5-20251001",
            "claude-sonnet-4-6",
            "claude-opus-4-8",
        ],
        index=0,
        help="Haiku — быстро и дёшево, Sonnet — баланс, Opus — максимум качества.",
    )
    do_recognize = cols[1].button("распознать", type="primary",
                                  disabled=(photo is None))

    if photo and do_recognize:
        try:
            data = photo.read()
            mime = photo.type or "image/jpeg"
            with st.spinner("Claude разбирает фото…"):
                guesses = describe_fridge_photo(data, mime_type=mime, model=model)
        except VisionUnavailable as exc:
            st.error(f"Vision: {exc}")
            return

        if not guesses:
            st.warning("Модель не нашла продуктов на фото.")
            return

        st.session_state["vision_guesses"] = [
            {
                "name": g.name,
                "qty": g.qty,
                "grams": g.grams or 0.0,
                "confidence": g.confidence,
                "note": g.note,
                "include": True,
            }
            for g in guesses
        ]
        st.success(f"Распознано продуктов: {len(guesses)}. "
                   "Проверьте список, поправьте веса и нажмите «добавить выбранные».")

    guesses = st.session_state.get("vision_guesses")
    if not guesses:
        return

    st.markdown("**распознанные продукты**")
    for i, g in enumerate(guesses):
        with st.container(border=True):
            row = st.columns([1, 3, 1, 1, 1])
            g["include"] = row[0].checkbox(
                "включить", value=g["include"],
                key=f"vg_inc_{i}", label_visibility="collapsed",
            )
            g["name"] = row[1].text_input(
                "название", value=g["name"], key=f"vg_name_{i}",
                label_visibility="collapsed",
            )
            g["qty"] = row[2].number_input(
                "шт.", value=float(g["qty"] or 0.0),
                min_value=0.0, max_value=100.0, step=1.0,
                key=f"vg_qty_{i}", label_visibility="collapsed",
            )
            g["grams"] = row[3].number_input(
                "граммы", value=float(g["grams"]),
                min_value=0.0, max_value=50000.0, step=10.0,
                key=f"vg_g_{i}", label_visibility="collapsed",
            )
            conf_color = {"high": "olive", "medium": "", "low": "ochre"}
            row[4].markdown(
                f'<span class="rv-pill {conf_color.get(g["confidence"], "")}">'
                f'{g["confidence"]}</span>',
                unsafe_allow_html=True,
            )
            if g["note"]:
                st.caption(f"📝 {g['note']}")

    btn_cols = st.columns([1, 1, 3])
    if btn_cols[0].button("добавить выбранные", type="primary",
                          key="vg_add"):
        from src.nutrition import find_product
        added = 0
        for g in guesses:
            if not g["include"]:
                continue
            if g["grams"] <= 0:
                continue
            match = find_product(g["name"])
            canonical = match[0].name if match else ""
            qty_disp = f' ({int(g["qty"])} шт)' if g["qty"] else ""
            pantry.add(PantryItem(
                id="",
                raw=f'{g["name"]}{qty_disp} — {g["grams"]:.0f} г · vision',
                name=g["name"],
                product_name=canonical,
                grams=float(g["grams"]),
                note=g["note"],
            ))
            added += 1
        _save_pantry()
        st.session_state.pop("vision_guesses", None)
        st.success(f"Добавлено в холодильник: {added} продуктов.")
        st.rerun()
    if btn_cols[1].button("сбросить", key="vg_reset"):
        st.session_state.pop("vision_guesses", None)
        st.rerun()


def _render_match_card(m) -> None:
    r = m.recipe
    title = r.get("title") or "Без названия"
    source = "🌱 стартовый" if r.get("_source") == "starter" else "📚 ваш"
    with st.container(border=True):
        top = st.columns([5, 2, 2])
        top[0].markdown(f"**{title}**")
        top[0].caption(f"{cats.label_of(r.get('category', ''))} · {source}")
        top[1].metric("Покрытие", f"{m.coverage:.0%}")
        top[2].metric("Готово", f"{m.matched_count}/{m.total_with_weights}")

        with st.expander("Подробно: что есть и что докупить"):
            if m.have:
                st.markdown("**✅ Уже есть в нужном объёме / частично**")
                st.dataframe(
                    [{"Продукт": s.product_name,
                      "Нужно, г": f"{s.needed_g:.0f}",
                      "Есть, г": f"{s.have_g:.0f}",
                      "Не хватает, г": f"{s.short_g:.0f}" if s.short_g else "—"}
                     for s in m.have],
                    use_container_width=True, hide_index=True,
                )
            if m.missing:
                st.markdown("**🛒 Докупить**")
                st.dataframe(
                    [{"Продукт": s.product_name,
                      "Объём, г": f"{s.short_g:.0f}"}
                     for s in m.missing],
                    use_container_width=True, hide_index=True,
                )
            if m.unmatched:
                st.caption(
                    "⚠️ Не сопоставлены с БД (не учитывались в покрытии): "
                    + ", ".join(s.line for s in m.unmatched)
                )

        if r.get("ingredients") and r.get("steps"):
            with st.expander("Полный рецепт"):
                st.markdown("**Ингредиенты**")
                for i in r["ingredients"]:
                    st.markdown(f"- {i}")
                st.markdown("**Приготовление**")
                for i, s in enumerate(r["steps"], 1):
                    st.markdown(f"{i}. {s}")


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
    elif page == "pantry":
        render_pantry()
    elif page == "diary":
        render_diary()
    elif page == "about":
        render_about()
    else:
        render_home()


if __name__ == "__main__":
    main()
