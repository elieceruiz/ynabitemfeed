# ============================================================
# ynab_api.py
# ============================================================
#
# Módulo encargado de comunicarse con la API de YNAB.
#
# FUNCIONES PRINCIPALES
# ---------------------
#
# 1. Detectar automáticamente el presupuesto Fresh Start.
# 2. Detectar automáticamente la cuenta dentro de ese presupuesto.
# 3. Obtener las categorías del presupuesto detectado.
# 4. Crear transacciones utilizando SIEMPRE los IDs actuales.
#
#
# IMPORTANTE
# ----------
#
# Antes:
#
#     BUDGET_ID
#     ACCOUNT_ID
#
# estaban amarrados manualmente a los Secrets de Streamlit.
#
# Esto causó el problema después de hacer Fresh Start:
#
#     Presupuesto viejo  -> BUDGET_ID viejo
#     Cuenta vieja       -> ACCOUNT_ID viejo
#
# Ahora:
#
#     YNAB_TOKEN
#          ↓
#     Buscar presupuesto Fresh Start
#          ↓
#     Obtener BUDGET_ID actual
#          ↓
#     Obtener cuentas actuales
#          ↓
#     Seleccionar ACCOUNT_ID actual
#          ↓
#     Trabajar con esos IDs
#
# De esta manera, un nuevo Fresh Start no debería requerir
# cambiar manualmente los IDs cada vez.
#
# ============================================================


# ------------------------------------------------------------
# IMPORTACIONES
# ------------------------------------------------------------

# requests permite realizar peticiones HTTP a la API de YNAB.
import requests

# Streamlit permite acceder a los Secrets configurados
# tanto localmente como en Streamlit Cloud.
import streamlit as st


# ============================================================
# CONFIGURACIÓN
# ============================================================

# ------------------------------------------------------------
# TOKEN DE YNAB
# ------------------------------------------------------------
#
# El token SÍ permanece en Secrets porque es una credencial
# privada y no debe estar escrito directamente en el código.
#
# En .streamlit/secrets.toml:
#
# YNAB_TOKEN = "..."
#
TOKEN = st.secrets["YNAB_TOKEN"]


# ------------------------------------------------------------
# NOMBRE DEL PRESUPUESTO QUE QUEREMOS DETECTAR
# ------------------------------------------------------------
#
# En su caso actual el presupuesto se llama:
#
#     YNAB — Fresh Start 2026
#
# No usamos el nombre completo para que el código también
# pueda detectar futuros presupuestos como:
#
#     YNAB — Fresh Start 2027
#     YNAB — Fresh Start 2028
#
# etc.
#
NOMBRE_FRESH_START = "fresh start"


# ------------------------------------------------------------
# NOMBRE DE LA CUENTA
# ------------------------------------------------------------
#
# >>> CORRECCIÓN IMPORTANTE
#
# Necesitamos una forma de saber QUÉ cuenta utilizar.
#
# Lo ideal es guardar solamente el nombre de la cuenta en
# Secrets, NO su ACCOUNT_ID.
#
# Ejemplo:
#
# ACCOUNT_NAME = "Bancolombia"
#
# De esta manera, después de un Fresh Start, el ID puede
# cambiar, pero el nombre de la cuenta sigue siendo el mismo.
#
# Si ACCOUNT_NAME todavía no existe en sus Secrets, el código
# intentará utilizar la primera cuenta activa encontrada.
#
ACCOUNT_NAME = st.secrets.get("ACCOUNT_NAME", "")


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def ynab_headers():
    """
    Devuelve los encabezados HTTP necesarios para comunicarnos
    con la API de YNAB.
    """

    return {
        "Authorization": f"Bearer {TOKEN}"
    }


# ------------------------------------------------------------
# OBTENER TODOS LOS PRESUPUESTOS
# ------------------------------------------------------------

def obtener_presupuestos():
    """
    Consulta todos los presupuestos disponibles en YNAB.

    Returns
    -------
    list
        Lista de presupuestos devueltos por YNAB.
    """

    # Endpoint oficial de YNAB para presupuestos.
    url = "https://api.ynab.com/v1/budgets"

    # Realizar petición GET.
    r = requests.get(
        url,
        headers=ynab_headers(),
        timeout=30
    )

    # Si YNAB devuelve un error HTTP, detener la ejecución.
    r.raise_for_status()

    # Convertir la respuesta a JSON.
    data = r.json()

    # Devolver la lista de presupuestos.
    return data["data"]["budgets"]


# ------------------------------------------------------------
# DETECTAR PRESUPUESTO FRESH START
# ------------------------------------------------------------

def obtener_budget_actual():
    """
    Busca automáticamente el presupuesto cuyo nombre contiene
    'Fresh Start'.

    Ejemplo:

        YNAB — Fresh Start 2026

    Returns
    -------
    dict
        Presupuesto detectado.

    Raises
    ------
    RuntimeError
        Si no se encuentra ningún presupuesto Fresh Start.
    """

    # Obtener todos los presupuestos disponibles.
    presupuestos = obtener_presupuestos()

    # Buscar un presupuesto cuyo nombre contenga
    # "fresh start", ignorando mayúsculas/minúsculas.
    coincidencias = [
        presupuesto
        for presupuesto in presupuestos
        if NOMBRE_FRESH_START in presupuesto["name"].lower()
    ]


    # --------------------------------------------------------
    # COMPROBAR RESULTADOS
    # --------------------------------------------------------

    # Si no encontramos ninguno, detenemos la aplicación.
    if not coincidencias:

        raise RuntimeError(
            "No se encontró ningún presupuesto cuyo nombre "
            "contenga 'Fresh Start'."
        )


    # --------------------------------------------------------
    # SI HAY VARIOS FRESH START
    # --------------------------------------------------------

    # >>> CORRECCIÓN
    #
    # Si existen varios presupuestos que contienen "Fresh Start",
    # no elegimos silenciosamente uno al azar.
    #
    # Los ordenamos por última modificación y utilizamos el más
    # recientemente modificado.
    #
    # Esto permite manejar nombres como:
    #
    #     YNAB — Fresh Start 2025
    #     YNAB — Fresh Start 2026
    #
    coincidencias.sort(
        key=lambda presupuesto: presupuesto.get(
            "last_modified_on"
        ) or "",
        reverse=True
    )


    # Tomar el primero después de ordenar.
    presupuesto = coincidencias[0]


    # --------------------------------------------------------
    # DEVOLVER EL PRESUPUESTO
    # --------------------------------------------------------

    return presupuesto


# ------------------------------------------------------------
# OBTENER CUENTAS DE UN PRESUPUESTO
# ------------------------------------------------------------

def obtener_cuentas(budget_id):
    """
    Obtiene todas las cuentas activas pertenecientes al
    presupuesto indicado.

    Parameters
    ----------
    budget_id : str
        ID actual del presupuesto.

    Returns
    -------
    list
        Lista de cuentas activas.
    """

    # Construir el endpoint utilizando el BUDGET_ID actual.
    url = (
        f"https://api.ynab.com/v1/budgets/"
        f"{budget_id}/accounts"
    )

    # Consultar YNAB.
    r = requests.get(
        url,
        headers=ynab_headers(),
        timeout=30
    )

    # Comprobar errores.
    r.raise_for_status()

    # Convertir respuesta a JSON.
    data = r.json()

    # Obtener cuentas.
    cuentas = data["data"]["accounts"]


    # --------------------------------------------------------
    # ELIMINAR CUENTAS BORRADAS
    # --------------------------------------------------------

    cuentas_activas = [
        cuenta
        for cuenta in cuentas
        if not cuenta["deleted"]
    ]


    return cuentas_activas


# ------------------------------------------------------------
# DETECTAR CUENTA ACTUAL
# ------------------------------------------------------------

def obtener_account_actual(budget_id):
    """
    Obtiene el ACCOUNT_ID actual dentro del presupuesto
    Fresh Start.

    La búsqueda se realiza preferentemente por nombre.

    Si ACCOUNT_NAME está configurado:
        busca esa cuenta.

    Si no está configurado:
        utiliza la primera cuenta activa disponible.

    Parameters
    ----------
    budget_id : str
        ID actual del presupuesto.

    Returns
    -------
    dict
        Información de la cuenta seleccionada.
    """

    # Obtener las cuentas del presupuesto actual.
    cuentas = obtener_cuentas(budget_id)


    # --------------------------------------------------------
    # COMPROBAR QUE EXISTAN CUENTAS
    # --------------------------------------------------------

    if not cuentas:

        raise RuntimeError(
            "El presupuesto Fresh Start no tiene "
            "ninguna cuenta activa."
        )


    # --------------------------------------------------------
    # BUSCAR POR NOMBRE
    # --------------------------------------------------------

    # Si configuramos ACCOUNT_NAME, intentamos encontrar
    # exactamente esa cuenta.
    if ACCOUNT_NAME:

        for cuenta in cuentas:

            if (
                cuenta["name"].strip().lower()
                == ACCOUNT_NAME.strip().lower()
            ):

                return cuenta


        # Si se especificó una cuenta pero no existe,
        # es mejor detenernos que registrar dinero en una
        # cuenta equivocada.
        raise RuntimeError(
            f"No se encontró la cuenta '{ACCOUNT_NAME}' "
            "dentro del presupuesto Fresh Start."
        )


    # --------------------------------------------------------
    # FALLBACK
    # --------------------------------------------------------

    # >>> CORRECCIÓN DE SEGURIDAD
    #
    # Si no tenemos ACCOUNT_NAME, usamos la primera cuenta
    # activa solamente como respaldo.
    #
    # Lo recomendable es configurar ACCOUNT_NAME en Secrets.
    return cuentas[0]


# ============================================================
# OBTENER CONTEXTO ACTUAL DE YNAB
# ============================================================

def obtener_contexto_ynab():
    """
    Obtiene simultáneamente:

        - presupuesto actual
        - BUDGET_ID actual
        - cuenta actual
        - ACCOUNT_ID actual

    Returns
    -------
    dict
        Información consolidada del presupuesto y cuenta.
    """

    # Detectar presupuesto Fresh Start.
    presupuesto = obtener_budget_actual()

    # Obtener su ID actual.
    budget_id = presupuesto["id"]

    # Detectar cuenta dentro de ese presupuesto.
    cuenta = obtener_account_actual(budget_id)

    # Obtener ID actual de la cuenta.
    account_id = cuenta["id"]


    # Devolver toda la información.
    return {
        "budget": presupuesto,
        "budget_id": budget_id,
        "account": cuenta,
        "account_id": account_id
    }


# ============================================================
# OBTENER TODAS LAS CATEGORÍAS
# ============================================================

def traer_categorias():
    """
    Retrieves all active categories from the CURRENT YNAB budget.

    >>> CORRECCIÓN:
    Ya NO utiliza BUDGET_ID desde Secrets.

    El presupuesto se detecta automáticamente.
    """

    # --------------------------------------------------------
    # DETECTAR PRESUPUESTO ACTUAL
    # --------------------------------------------------------

    contexto = obtener_contexto_ynab()

    # Extraer el BUDGET_ID actual.
    budget_id = contexto["budget_id"]


    # --------------------------------------------------------
    # ENDPOINT DE CATEGORÍAS
    # --------------------------------------------------------

    url = (
        f"https://api.ynab.com/v1/budgets/"
        f"{budget_id}/categories"
    )


    # --------------------------------------------------------
    # PETICIÓN
    # --------------------------------------------------------

    r = requests.get(
        url,
        headers=ynab_headers(),
        timeout=30
    )

    # Comprobar errores.
    r.raise_for_status()

    # Convertir respuesta.
    data = r.json()


    # --------------------------------------------------------
    # CREAR LISTA SIMPLIFICADA
    # --------------------------------------------------------

    categorias = []


    # YNAB organiza las categorías dentro de grupos.
    for group in data["data"]["category_groups"]:

        # Recorrer categorías del grupo.
        for cat in group["categories"]:

            # Ignorar categorías eliminadas.
            if not cat["deleted"]:

                categorias.append({

                    # Nombre mostrado en la interfaz.
                    "nombre": (
                        f"{group['name']} → "
                        f"{cat['name']}"
                    ),

                    # ID que necesita YNAB.
                    "id": cat["id"]
                })


    # Devolver categorías.
    return categorias


# ============================================================
# CREAR TRANSACCIÓN
# ============================================================

def crear_transaccion(
    account_id,
    categoria_id,
    payee,
    amount,
    fecha,
    memo
):
    """
    Creates a transaction inside the CURRENT YNAB budget.

    Parameters
    ----------
    account_id : str
        ACCOUNT_ID de la cuenta donde se registrará
        la transacción.

    categoria_id : str
        ID de la categoría.

    payee : str
        Nombre del comercio/proveedor.

    amount : float
        Valor normal de la transacción.
        Ejemplo:
            6800

    fecha : str
        Fecha en formato:
            YYYY-MM-DD

    memo : str
        Información adicional de la transacción.
    """


    # --------------------------------------------------------
    # DETECTAR PRESUPUESTO ACTUAL
    # --------------------------------------------------------

    # >>> CORRECCIÓN PRINCIPAL
    #
    # La transacción YA NO utiliza:
    #
    #     BUDGET = st.secrets["BUDGET_ID"]
    #
    # Utiliza el BUDGET_ID que YNAB tiene actualmente.
    contexto = obtener_contexto_ynab()

    budget_id = contexto["budget_id"]


    # --------------------------------------------------------
    # ENDPOINT DE TRANSACCIONES
    # --------------------------------------------------------

    url = (
        f"https://api.ynab.com/v1/budgets/"
        f"{budget_id}/transactions"
    )


    # --------------------------------------------------------
    # CONSTRUIR PAYLOAD
    # --------------------------------------------------------

    payload = {
        "transaction": {

            # Cuenta donde se registrará el gasto.
            "account_id": account_id,

            # Fecha de la transacción.
            "date": fecha,

            # ------------------------------------------------
            # YNAB UTILIZA MILLIUNITS
            # ------------------------------------------------
            #
            # Ejemplo:
            #
            # 6.800 COP
            #
            # se envía como:
            #
            # -6.800.000 milliunits
            #
            # El signo negativo representa gasto.
            "amount": -int(amount * 1000),

            # Nombre del proveedor/comercio.
            "payee_name": payee,

            # Información adicional.
            "memo": memo,

            # Categoría.
            "category_id": categoria_id,

            # La transacción ya está conciliada.
            "cleared": "cleared"
        }
    }


    # --------------------------------------------------------
    # ENVIAR TRANSACCIÓN
    # --------------------------------------------------------

    r = requests.post(
        url,
        json=payload,
        headers=ynab_headers(),
        timeout=30
    )


    # --------------------------------------------------------
    # COMPROBAR RESPUESTA
    # --------------------------------------------------------

    # >>> CORRECCIÓN
    #
    # Antes el código hacía:
    #
    #     requests.post(...)
    #
    # y no comprobaba si YNAB realmente aceptó
    # la transacción.
    #
    # Ahora, si YNAB devuelve un error, la aplicación
    # lo detectará inmediatamente.
    r.raise_for_status()


    # --------------------------------------------------------
    # DEVOLVER RESPUESTA
    # --------------------------------------------------------

    # Devolvemos la respuesta de YNAB por si el frontend
    # necesita conocer el ID de la transacción creada.
    return r.json()