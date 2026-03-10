# gmail_fetch.py

# ---------------------------------------
# IMPORTS
# ---------------------------------------

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import os
import pickle
import base64
import zipfile
import io


# ---------------------------------------
# PERMISOS GMAIL
# ---------------------------------------

# Solo lectura del correo
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


# ---------------------------------------
# CONECTAR CON GMAIL
# ---------------------------------------

def conectar_gmail():
    """
    Abre conexión con Gmail usando OAuth2.

    Si ya existe token guardado lo usa.
    Si no existe abre login de Google.
    """

    creds = None

    # Si ya tenemos token guardado
    if os.path.exists("token.json"):
        with open("token.json", "rb") as token:
            creds = pickle.load(token)

    # Si no hay credenciales válidas
    if not creds or not creds.valid:

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())

        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json",
                SCOPES
            )

            creds = flow.run_local_server(port=0, open_browser=False)

        # Guardar token para futuras ejecuciones
        with open("token.json", "wb") as token:
            pickle.dump(creds, token)

    # Crear servicio Gmail
    service = build("gmail", "v1", credentials=creds)

    return service


# ---------------------------------------
# BUSCAR CORREOS CON FACTURAS
# ---------------------------------------

def obtener_adjuntos(service, dias):

    """
    Busca correos con adjuntos XML o ZIP
    y devuelve lista de archivos encontrados.
    """

    results = service.users().messages().list(
        userId="me",
        q=f"has:attachment (filename:xml OR filename:zip) newer_than:{dias}d"
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

        for part in parts:

            filename = part.get("filename")

            if not filename:
                continue

            if filename.endswith(".xml") or filename.endswith(".zip"):

                body = part.get("body", {})

                if "data" in body:

                    data = body["data"]

                else:

                    att_id = body.get("attachmentId")

                    att = service.users().messages().attachments().get(
                        userId="me",
                        messageId=m["id"],
                        id=att_id
                    ).execute()

                    data = att["data"]

                file_bytes = base64.urlsafe_b64decode(data)

                archivos.append({
                    "filename": filename,
                    "data": file_bytes
                })

    return archivos

# ---------------------------------------
# EXTRAER XML SI EL ARCHIVO ES ZIP
# ---------------------------------------

def extraer_xml(archivo):

    """
    Recibe un archivo (xml o zip)
    y devuelve el XML listo para parsear
    """

    filename = archivo["filename"]
    data = archivo["data"]

    # Si ya es XML
    if filename.endswith(".xml"):
        return data

    # Si es ZIP buscar XML dentro
    if filename.endswith(".zip"):

        with zipfile.ZipFile(io.BytesIO(data)) as z:

            for name in z.namelist():

                if name.endswith(".xml"):
                    return z.read(name)

    return None
