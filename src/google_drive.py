"""Google Drive: загрузка markdown/json рецептов в выбранную папку.

Используем сервисный аккаунт (Streamlit secrets → gcp_service_account).
Папка должна быть расшарена с email сервисного аккаунта (роль Editor).
"""
from __future__ import annotations

import io
import json
from dataclasses import dataclass
from typing import Any, Optional

try:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaIoBaseUpload
except ImportError:  # pragma: no cover
    Credentials = None  # type: ignore[assignment]
    build = None  # type: ignore[assignment]
    HttpError = Exception  # type: ignore[assignment,misc]
    MediaIoBaseUpload = None  # type: ignore[assignment]


SCOPES = ["https://www.googleapis.com/auth/drive"]


class DriveError(RuntimeError):
    pass


@dataclass
class UploadedFile:
    file_id: str
    name: str
    mime_type: str
    web_link: str


class DriveClient:
    def __init__(self, service_account_info: dict[str, Any], folder_id: str):
        if Credentials is None or build is None:
            raise DriveError(
                "google-api-python-client/google-auth не установлены. "
                "Проверьте requirements.txt."
            )
        if not folder_id:
            raise DriveError("Не задан folder_id целевой папки Google Drive.")
        try:
            creds = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
        except Exception as exc:  # pragma: no cover
            raise DriveError(f"Не удалось разобрать service-account JSON: {exc}") from exc
        self._service = build("drive", "v3", credentials=creds, cache_discovery=False)
        self.folder_id = folder_id

    # ----- внутренние утилиты ------------------------------------------------

    def _find_by_name(self, name: str, mime_type: Optional[str] = None) -> Optional[dict[str, Any]]:
        safe = name.replace("'", "\\'")
        q = f"name = '{safe}' and '{self.folder_id}' in parents and trashed = false"
        if mime_type:
            q += f" and mimeType = '{mime_type}'"
        try:
            resp = self._service.files().list(
                q=q,
                fields="files(id, name, mimeType, webViewLink)",
                pageSize=1,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()
        except HttpError as exc:
            raise DriveError(f"Drive API: {exc}") from exc
        files = resp.get("files", [])
        return files[0] if files else None

    def _upload(self, name: str, data: bytes, mime_type: str, convert_to_google_doc: bool) -> UploadedFile:
        media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime_type, resumable=False)
        target_mime = "application/vnd.google-apps.document" if convert_to_google_doc else mime_type
        existing = self._find_by_name(name, mime_type=target_mime)
        try:
            if existing:
                file = self._service.files().update(
                    fileId=existing["id"],
                    media_body=media,
                    fields="id, name, mimeType, webViewLink",
                    supportsAllDrives=True,
                ).execute()
            else:
                body = {"name": name, "parents": [self.folder_id]}
                if convert_to_google_doc:
                    body["mimeType"] = "application/vnd.google-apps.document"
                file = self._service.files().create(
                    body=body,
                    media_body=media,
                    fields="id, name, mimeType, webViewLink",
                    supportsAllDrives=True,
                ).execute()
        except HttpError as exc:
            raise DriveError(f"Drive API: {exc}") from exc
        return UploadedFile(
            file_id=file["id"],
            name=file["name"],
            mime_type=file["mimeType"],
            web_link=file.get("webViewLink", ""),
        )

    # ----- публичные методы --------------------------------------------------

    def list_recipes(self, page_size: int = 100) -> list[dict[str, Any]]:
        q = f"'{self.folder_id}' in parents and trashed = false"
        try:
            resp = self._service.files().list(
                q=q,
                fields="files(id, name, mimeType, modifiedTime, webViewLink)",
                pageSize=page_size,
                orderBy="modifiedTime desc",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()
        except HttpError as exc:
            raise DriveError(f"Drive API: {exc}") from exc
        return resp.get("files", [])

    def save_markdown_as_doc(self, title: str, markdown: str) -> UploadedFile:
        """Сохраняем markdown как Google Doc (с конвертацией)."""
        name = title.strip() or "Без названия"
        return self._upload(
            name=name,
            data=markdown.encode("utf-8"),
            mime_type="text/markdown",
            convert_to_google_doc=True,
        )

    def save_markdown_file(self, title: str, markdown: str) -> UploadedFile:
        """Сохраняем как .md-файл без конвертации."""
        name = title.strip() or "recipe"
        if not name.lower().endswith(".md"):
            name = f"{name}.md"
        return self._upload(
            name=name,
            data=markdown.encode("utf-8"),
            mime_type="text/markdown",
            convert_to_google_doc=False,
        )

    def save_json_backup(self, title: str, payload: dict[str, Any]) -> UploadedFile:
        name = title.strip() or "recipe"
        if not name.lower().endswith(".json"):
            name = f"{name}.json"
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        return self._upload(
            name=name,
            data=data,
            mime_type="application/json",
            convert_to_google_doc=False,
        )

    def load_recipe_json(self, file_id: str) -> Optional[dict[str, Any]]:
        """Считываем JSON-бэкап рецепта (mime application/json)."""
        try:
            text = self.download_text(file_id, "application/json")
            return json.loads(text)
        except (DriveError, json.JSONDecodeError):
            return None

    def list_recipe_jsons(self) -> list[dict[str, Any]]:
        """Все .json-файлы в папке (наши бэкапы рецептов) c parsed payload."""
        files = self.list_recipes(page_size=500)
        result: list[dict[str, Any]] = []
        for f in files:
            if f["mimeType"] != "application/json":
                continue
            if f["name"] in ("meal_log.json", "pantry.json"):
                continue
            payload = self.load_recipe_json(f["id"])
            if not payload:
                continue
            result.append({
                "file_id": f["id"],
                "name": f["name"],
                "modified": f.get("modifiedTime", ""),
                "web_link": f.get("webViewLink", ""),
                "payload": payload,
            })
        return result

    def load_meal_log(self) -> tuple[dict[str, Any], Optional[str]]:
        """Возвращает (payload, file_id). Если файла нет — ({}, None)."""
        existing = self._find_by_name("meal_log.json", mime_type="application/json")
        if not existing:
            return {}, None
        payload = self.load_recipe_json(existing["id"]) or {}
        return payload, existing["id"]

    def save_meal_log(self, payload: dict[str, Any]) -> UploadedFile:
        """Перезаписывает meal_log.json целиком."""
        return self._upload(
            name="meal_log.json",
            data=json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
            mime_type="application/json",
            convert_to_google_doc=False,
        )

    def load_pantry(self) -> tuple[dict[str, Any], Optional[str]]:
        existing = self._find_by_name("pantry.json", mime_type="application/json")
        if not existing:
            return {}, None
        payload = self.load_recipe_json(existing["id"]) or {}
        return payload, existing["id"]

    def save_pantry(self, payload: dict[str, Any]) -> UploadedFile:
        return self._upload(
            name="pantry.json",
            data=json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
            mime_type="application/json",
            convert_to_google_doc=False,
        )

    def download_text(self, file_id: str, mime_type: str) -> str:
        """Скачиваем содержимое файла из папки как текст (для Google Doc — экспорт в md)."""
        try:
            if mime_type == "application/vnd.google-apps.document":
                data = self._service.files().export(
                    fileId=file_id,
                    mimeType="text/plain",
                ).execute()
                if isinstance(data, bytes):
                    return data.decode("utf-8", errors="replace")
                return str(data)
            req = self._service.files().get_media(fileId=file_id, supportsAllDrives=True)
            buf = io.BytesIO()
            from googleapiclient.http import MediaIoBaseDownload

            downloader = MediaIoBaseDownload(buf, req)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            return buf.getvalue().decode("utf-8", errors="replace")
        except HttpError as exc:
            raise DriveError(f"Drive API: {exc}") from exc
