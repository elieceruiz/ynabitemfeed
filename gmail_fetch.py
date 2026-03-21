# gmail_fetch.py

# ---------------------------------------
# IMPORTS
# ---------------------------------------

import streamlit as st
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import base64
import zipfile
import io

# ---------------------------------------
# PERMISOS GMAIL
# ---------------------------------------

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# ---------------------------------------
# CONECTAR CON GMAIL (USANDO SECRETS)
# ---------------------------------------

def conectar_gmail():

    creds = Credentials(
        None,
        refresh_token=st.secrets["GOOGLE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=st.secrets["GOOGLE_CLIENT_ID"],
        client_secret=st.secrets["GOOGLE_CLIENT_SECRET"],
        scopes=SCOPES
    )

    service = build("gmail", "v1", credentials=creds)

    return service


# ---------------------------------------
# FUNCIÓN RECURSIVA PARA BUSCAR ADJUNTOS
# ---------------------------------------

def _recorrer_partes(parts, msg_id, service, archivos):

    for part in parts:

        filename = part.get("filename")

        if filename:

            filename = filename.lower()

            if filename.endswith(".xml") or filename.endswith(".zip"):

                body = part.get("body", {})

                if "data" in body:

                    data = body["data"]

                else:

                    att_id = body.get("attachmentId")

                    if not att_id:
                        continue

                    att = service.users().messages().attachments().get(
                        userId="me",
                        messageId=msg_id,
                        id=att_id
                    ).execute()

                    data = att["data"]

                file_bytes = base64.urlsafe_b64decode(data)

                archivos.append({
                    "filename": filename,
                    "data": file_bytes
                })

        # Buscar dentro de partes internas (correos reenviados)
        if "parts" in part:
            _recorrer_partes(part["parts"], msg_id, service, archivos)


# ---------------------------------------
# BUSCAR CORREOS CON FACTURAS
# ---------------------------------------

def obtener_adjuntos(service, dias):

    results = service.users().messages().list(
        userId="me",
        q=f"has:attachment newer_than:{dias}d"
    ).execute()

    mensajes = results.get("messages", [])

    archivos = []

    for m in mensajes:

        msg = service.users().messages().get(
            userId="me",
            id=m["id"]
        ).execute()

        payload = msg.get("payload", {})
        parts = payload.get("parts", [])

        _recorrer_partes(parts, m["id"], service, archivos)

    return archivos


# ---------------------------------------
# EXTRAER XML SI EL ARCHIVO ES ZIP
# ---------------------------------------

def extraer_xml(archivo):

    filename = archivo["filename"]
    data = archivo["data"]

    if filename.endswith(".xml"):
        return data

    if filename.endswith(".zip"):

        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:

                for name in z.namelist():

                    if name.lower().endswith(".xml"):
                        return z.read(name)

        except zipfile.BadZipFile:
            return None

    return None
