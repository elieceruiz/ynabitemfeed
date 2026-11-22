"""Lectura de adjuntos XML/ZIP desde Gmail (solo lectura)."""
import base64
import io
import zipfile

import streamlit as st
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def conectar_gmail():
    credentials = Credentials(
        None,
        refresh_token=st.secrets["GOOGLE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=st.secrets["GOOGLE_CLIENT_ID"],
        client_secret=st.secrets["GOOGLE_CLIENT_SECRET"],
        scopes=SCOPES,
    )
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def _decodificar_adjunto(data):
    if not data:
        return b""
    data += "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data.encode("ascii"))


def _recorrer_partes(parts, msg_id, service, archivos):
    for part in parts or []:
        original_name = part.get("filename", "")
        filename = original_name.strip()
        body = part.get("body", {}) or {}

        if filename and filename.casefold().endswith((".xml", ".zip")):
            data = body.get("data")
            if data is None:
                attachment_id = body.get("attachmentId")
                if attachment_id:
                    attachment = (
                        service.users().messages().attachments()
                        .get(userId="me", messageId=msg_id, id=attachment_id)
                        .execute()
                    )
                    data = attachment.get("data")

            if data:
                archivos.append({
                    "filename": filename,
                    "data": _decodificar_adjunto(data),
                    "message_id": msg_id,
                })

        nested = part.get("parts")
        if nested:
            _recorrer_partes(nested, msg_id, service, archivos)


def obtener_adjuntos(service, dias):
    """Recorre todas las páginas de Gmail y descarga adjuntos XML/ZIP."""
    archivos = []
    page_token = None

    while True:
        response = service.users().messages().list(
            userId="me",
            q=f"has:attachment newer_than:{int(dias)}d",
            maxResults=100,
            pageToken=page_token,
        ).execute()

        for message in response.get("messages", []):
            detail = service.users().messages().get(
                userId="me", id=message["id"], format="full"
            ).execute()
            payload = detail.get("payload", {})
            parts = payload.get("parts") or [payload]
            _recorrer_partes(parts, message["id"], service, archivos)

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return archivos


def extraer_xml(archivo):
    filename = archivo.get("filename", "").casefold()
    data = archivo.get("data", b"")

    if filename.endswith(".xml"):
        return data

    if filename.endswith(".zip"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                xml_names = sorted(
                    name for name in archive.namelist()
                    if name.casefold().endswith(".xml") and not name.endswith("/")
                )
                return archive.read(xml_names[0]) if xml_names else None
        except (zipfile.BadZipFile, OSError, KeyError):
            return None

    return None
