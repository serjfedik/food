"""Recipe Vault — Streamlit-приложение для оцифровки и хранения рецептов.

Сценарий:
1. «Загрузить рецепт» — PDF/DOCX/фото → текст (OCR если нужен).
2. «Адаптировать рецепт» — правка артефактов и структуры в реальном времени.
3. «Сохранить» — синк в Google Drive (Google Doc + JSON-бэкап).
4. «Библиотека» — список рецептов из подключённой папки.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

import streamlit as st

from src.file_loader import LoadResult, SUPPORTED_EXTS, load_file
from src.google_drive import DriveClient, DriveError
from src.recipe_parser import Recipe, parse_recipe


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
        "stage": "upload",            # upload | adapt | save
        "raw_text": "",               # текст после OCR/парсинга, до правки
        "load_meta": None,            # LoadResult
        "recipe": Recipe(),           # текущая структура рецепта
        "last_filename": "",
        "saved_links": [],            # история сохранений в Drive
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


def _drive_status_sidebar() -> None:
    client = _get_drive_client()
    with st.sidebar:
        st.markdown("### Google Drive")
        if client is None:
            st.warning(
                "Drive не подключён. Заполните `.streamlit/secrets.toml` "
                "(см. `secrets.toml.example`) или Secrets в Streamlit Cloud."
            )
            with st.expander("Как подключить", expanded=False):
                st.markdown(
                    "1. В Google Cloud Console создайте **Service Account** и ключ JSON.\n"
                    "2. Включите Google Drive API для проекта.\n"
                    "3. В Google Drive создайте папку и расшарьте её с email сервисного аккаунта "
                    "(права Editor).\n"
                    "4. Скопируйте `folder_id` из URL папки.\n"
                    "5. Перенесите содержимое JSON в `[gcp_service_account]` секции secrets, "
                    "а `folder_id` — в `[google_drive]`."
                )
        else:
            st.success(f"Папка: `{client.folder_id}`")


# ---------------------------------------------------------------------------
# UI: загрузка
# ---------------------------------------------------------------------------

def render_upload() -> None:
    st.subheader("1. Загрузить рецепт")
    st.caption(
        "Поддерживаются PDF, DOCX, фото и сканы (PNG/JPG/TIFF/WebP) и .txt. "
        "Для рукописных/сканированных будет включён OCR (русский + английский)."
    )

    col1, col2 = st.columns([2, 1])
    with col1:
        uploaded = st.file_uploader(
            "Файл рецепта",
            type=[e.lstrip(".") for e in SUPPORTED_EXTS],
            accept_multiple_files=False,
        )
    with col2:
        force_ocr = st.checkbox(
            "Принудительно OCR (для PDF-сканов без текстового слоя)",
            value=False,
        )
        langs = st.text_input("Языки OCR", value="rus+eng", help="Коды tesseract через '+'")

    if uploaded is None:
        st.info("Загрузите файл, чтобы продолжить.")
        return

    if st.button("Распознать и продолжить →", type="primary"):
        with st.spinner("Читаю файл…"):
            try:
                data = uploaded.read()
                result = load_file(
                    filename=uploaded.name,
                    data=data,
                    force_ocr=force_ocr,
                    langs=langs.strip() or None,
                )
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
        st.session_state.stage = "adapt"
        st.rerun()


# ---------------------------------------------------------------------------
# UI: адаптация / редактирование
# ---------------------------------------------------------------------------

def _render_load_summary(meta: Optional[LoadResult]) -> None:
    if meta is None:
        return
    cols = st.columns(4)
    cols[0].metric("Источник", meta.source_type)
    cols[1].metric("OCR", "да" if meta.ocr_used else "нет")
    cols[2].metric("Страниц", meta.pages or "—")
    cols[3].metric("Символов", len(meta.text))
    if meta.warnings:
        with st.expander("Предупреждения парсинга", expanded=False):
            for w in meta.warnings:
                st.write(f"• {w}")


def _list_editor(label: str, items: list[str], key: str, height: int = 220) -> list[str]:
    """Простой текстовый редактор списка: по строке на элемент."""
    text = st.text_area(
        label,
        value="\n".join(items),
        key=key,
        height=height,
        help="Каждый элемент с новой строки. Пустые строки игнорируются.",
    )
    return [line.strip() for line in text.split("\n") if line.strip()]


def render_adapt() -> None:
    st.subheader("2. Адаптировать рецепт")
    st.caption(
        "Слева — сырой распознанный текст (правьте артефакты OCR). "
        "Справа — структурированные поля, которые попадут в Google Doc."
    )
    _render_load_summary(st.session_state.load_meta)

    left, right = st.columns([1, 1])

    with left:
        st.markdown("**Сырой текст (после распознавания)**")
        new_raw = st.text_area(
            "raw_text",
            value=st.session_state.raw_text,
            height=520,
            label_visibility="collapsed",
        )
        sub_cols = st.columns(2)
        if sub_cols[0].button("Перепарсить из текста"):
            st.session_state.raw_text = new_raw
            st.session_state.recipe = parse_recipe(new_raw)
            st.rerun()
        if sub_cols[1].button("Сбросить правки структуры"):
            st.session_state.recipe = parse_recipe(st.session_state.raw_text)
            st.rerun()
        # сохраняем правку в сыром тексте даже без перепарса
        st.session_state.raw_text = new_raw

    with right:
        recipe: Recipe = st.session_state.recipe
        recipe.title = st.text_input("Название", value=recipe.title)
        meta_cols = st.columns(2)
        recipe.servings = meta_cols[0].text_input("Порции", value=recipe.servings)
        recipe.time = meta_cols[1].text_input("Время", value=recipe.time)

        recipe.ingredients = _list_editor(
            "Ингредиенты",
            recipe.ingredients,
            key="ingredients_edit",
            height=200,
        )
        recipe.steps = _list_editor(
            "Шаги приготовления",
            recipe.steps,
            key="steps_edit",
            height=240,
        )
        recipe.notes = st.text_area("Заметки", value=recipe.notes, height=100)

        st.session_state.recipe = recipe

    st.divider()
    st.markdown("**Предпросмотр (Markdown)**")
    md = st.session_state.recipe.to_markdown()
    st.markdown(md)

    nav = st.columns([1, 1, 4])
    if nav[0].button("← К загрузке"):
        st.session_state.stage = "upload"
        st.rerun()
    if nav[1].button("Сохранить →", type="primary"):
        st.session_state.stage = "save"
        st.rerun()


# ---------------------------------------------------------------------------
# UI: сохранение в Drive
# ---------------------------------------------------------------------------

def render_save() -> None:
    st.subheader("3. Сохранить и синхронизировать")
    recipe: Recipe = st.session_state.recipe
    md = recipe.to_markdown()

    if not recipe.title.strip():
        st.warning("Пустое название. Введите его на шаге адаптации.")

    preview_cols = st.columns([1, 1])
    with preview_cols[0]:
        st.markdown("**Markdown, который уйдёт в Google Doc**")
        st.code(md, language="markdown")
    with preview_cols[1]:
        st.markdown("**JSON-бэкап (для восстановления структуры)**")
        payload = {
            "saved_at": datetime.utcnow().isoformat() + "Z",
            "source_filename": st.session_state.last_filename,
            "recipe": recipe.to_dict(),
        }
        st.code(json.dumps(payload, ensure_ascii=False, indent=2), language="json")

    client = _get_drive_client()
    options_cols = st.columns(3)
    save_as_doc = options_cols[0].checkbox("Google Doc (.gdoc)", value=True)
    save_md = options_cols[1].checkbox("Markdown файл (.md)", value=False)
    save_json = options_cols[2].checkbox("JSON-бэкап (.json)", value=True)

    nav = st.columns([1, 1, 2])
    if nav[0].button("← К редактированию"):
        st.session_state.stage = "adapt"
        st.rerun()

    download_name = (recipe.title.strip() or "recipe").replace("/", "_")
    nav[1].download_button(
        "⬇️ Скачать .md",
        data=md.encode("utf-8"),
        file_name=f"{download_name}.md",
        mime="text/markdown",
    )

    if nav[2].button("☁️ Сохранить в Google Drive", type="primary", disabled=(client is None)):
        if client is None:
            st.error("Drive не подключён.")
            return
        results = []
        with st.spinner("Загружаю в Drive…"):
            try:
                if save_as_doc:
                    results.append(client.save_markdown_as_doc(recipe.title, md))
                if save_md:
                    results.append(client.save_markdown_file(recipe.title, md))
                if save_json:
                    results.append(client.save_json_backup(recipe.title, payload))
            except DriveError as exc:
                st.error(f"Ошибка Drive: {exc}")
                return
        st.success(f"Сохранено файлов: {len(results)}")
        for f in results:
            st.markdown(f"• [{f.name}]({f.web_link}) · `{f.mime_type}`")
            st.session_state.saved_links.append(
                {"name": f.name, "link": f.web_link, "mime": f.mime_type}
            )


# ---------------------------------------------------------------------------
# UI: библиотека
# ---------------------------------------------------------------------------

def render_library() -> None:
    st.subheader("Библиотека рецептов")
    client = _get_drive_client()
    if client is None:
        st.info("Подключите Google Drive в sidebar, чтобы увидеть рецепты из папки.")
        return
    if st.button("Обновить список"):
        st.cache_data.clear()

    @st.cache_data(show_spinner=False, ttl=60)
    def _cached_list(folder_id: str) -> list[dict[str, Any]]:
        return client.list_recipes(page_size=200)

    try:
        files = _cached_list(client.folder_id)
    except DriveError as exc:
        st.error(f"Drive: {exc}")
        return

    if not files:
        st.info("В папке пока пусто.")
        return

    for f in files:
        with st.container(border=True):
            top = st.columns([5, 2, 1])
            top[0].markdown(f"**[{f['name']}]({f.get('webViewLink', '#')})**")
            top[1].caption(f.get("modifiedTime", "—"))
            top[2].caption(f["mimeType"].rsplit(".", 1)[-1])
            if f["mimeType"] in (
                "application/vnd.google-apps.document",
                "text/markdown",
                "text/plain",
                "application/json",
            ):
                if st.button("📥 Открыть в редакторе", key=f"open_{f['id']}"):
                    try:
                        text = client.download_text(f["id"], f["mimeType"])
                    except DriveError as exc:
                        st.error(f"Не удалось скачать: {exc}")
                        continue
                    if f["mimeType"] == "application/json":
                        try:
                            data = json.loads(text)
                            recipe = Recipe.from_dict(data.get("recipe", data))
                        except json.JSONDecodeError:
                            st.error("Файл повреждён.")
                            continue
                        st.session_state.recipe = recipe
                        st.session_state.raw_text = recipe.raw_text or recipe.to_markdown()
                    else:
                        st.session_state.raw_text = text
                        st.session_state.recipe = parse_recipe(text)
                    st.session_state.last_filename = f["name"]
                    st.session_state.stage = "adapt"
                    st.rerun()


# ---------------------------------------------------------------------------
# Главный layout
# ---------------------------------------------------------------------------

def main() -> None:
    st.title("🍲 Recipe Vault")
    st.caption("Оцифровка, адаптация и облачное хранение рецептов.")

    _drive_status_sidebar()
    with st.sidebar:
        st.markdown("### Навигация")
        page = st.radio(
            "",
            ("Редактор", "Библиотека"),
            label_visibility="collapsed",
        )
        if page == "Редактор":
            st.markdown("### Шаги")
            st.markdown(
                f"- {'**▶ '+ 'Загрузка**' if st.session_state.stage == 'upload' else 'Загрузка'}"
            )
            st.markdown(
                f"- {'**▶ '+ 'Адаптация**' if st.session_state.stage == 'adapt' else 'Адаптация'}"
            )
            st.markdown(
                f"- {'**▶ '+ 'Сохранение**' if st.session_state.stage == 'save' else 'Сохранение'}"
            )
            if st.button("Начать новый рецепт"):
                st.session_state.stage = "upload"
                st.session_state.raw_text = ""
                st.session_state.recipe = Recipe()
                st.session_state.load_meta = None
                st.rerun()

        if st.session_state.saved_links:
            st.markdown("### Недавно сохранено")
            for link in st.session_state.saved_links[-5:][::-1]:
                st.markdown(f"• [{link['name']}]({link['link']})")

    if page == "Библиотека":
        render_library()
        return

    stage = st.session_state.stage
    if stage == "upload":
        render_upload()
    elif stage == "adapt":
        render_adapt()
    elif stage == "save":
        render_save()


if __name__ == "__main__":
    main()
