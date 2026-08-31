# ============================================================
# app.py
# ============================================================
#
# Aplicación:
#
#     Factura → YNAB
#
# Flujo:
#
# 1. Buscar facturas en Gmail.
# 2. Extraer el XML.
# 3. Leer productos, fecha, proveedor y total.
# 4. Obtener las categorías ACTUALES de YNAB.
# 5. Permitir asignar categorías.
# 6. Guardar memoria producto → categoría en MongoDB.
# 7. Crear las transacciones en YNAB.
#
# ============================================================


# ------------------------------------------
# IMPORTACIONES
# ------------------------------------------

# Streamlit es el framework que usamos para
# construir la interfaz web.
import streamlit as st

# io permite trabajar con los bytes del XML
# como si fueran un archivo.
import io


# ------------------------------------------
# LECTOR DE FACTURAS
# ------------------------------------------

# Función que lee el XML de la factura electrónica
# y devuelve:
#
# items
# fecha
# proveedor
# total_factura
from parser_xml import leer_factura


# ------------------------------------------
# API DE YNAB
# ------------------------------------------

# traer_categorias:
#     Obtiene las categorías del Plan actual.
#
# crear_transaccion:
#     Crea una transacción en YNAB.
#
# obtener_contexto_ynab:
#     >>> CORRECCIÓN
#     Detecta automáticamente:
#
#         - Plan actual
#         - BUDGET_ID actual
#         - Cuenta actual
#         - ACCOUNT_ID actual
#
#     Esto evita depender del ACCOUNT_ID viejo
#     guardado manualmente en Secrets.
from ynab_api import (
    traer_categorias,
    crear_transaccion,
    obtener_contexto_ynab
)


# ------------------------------------------
# MONGO
# ------------------------------------------

# Colección Mongo donde guardamos memoria:
#
# producto → categoría
from db import productos


# ------------------------------------------
# GMAIL
# ------------------------------------------

# Funciones utilizadas para:
#
# 1. Conectarnos a Gmail.
# 2. Obtener adjuntos.
# 3. Extraer XML.
from gmail_fetch import (
    conectar_gmail,
    obtener_adjuntos,
    extraer_xml
)


# ============================================================
# CONFIGURACIÓN YNAB
# ============================================================

# >>> CORRECCIÓN PRINCIPAL
#
# ANTES:
#
# ACCOUNT_ID = st.secrets["ACCOUNT_ID"]
#
# Eso significaba que la aplicación utilizaba SIEMPRE
# el ACCOUNT_ID guardado en Secrets.
#
# Después de un Fresh Start ese ID puede cambiar.
#
# AHORA:
#
# La aplicación consulta YNAB y obtiene:
#
#     Plan actual
#     Cuenta actual
#     ACCOUNT_ID actual
#
# No necesitamos definir ACCOUNT_ID manualmente aquí.


# ------------------------------------------------------------
# OBTENER CONTEXTO ACTUAL DE YNAB
# ------------------------------------------------------------

# Consultamos YNAB para saber qué Plan y qué cuenta
# estamos utilizando actualmente.
#
# Esto se ejecuta al cargar la aplicación.
try:

    contexto_ynab = obtener_contexto_ynab()

    # ID actual del Plan.
    BUDGET_ID_ACTUAL = contexto_ynab["budget_id"]

    # Nombre actual del Plan.
    PLAN_NOMBRE = contexto_ynab["budget"]["name"]

    # Información de la cuenta actual.
    CUENTA = contexto_ynab["account"]

    # ID actual de la cuenta.
    ACCOUNT_ID_ACTUAL = contexto_ynab["account_id"]

    # Nombre de la cuenta.
    CUENTA_NOMBRE = CUENTA["name"]

    # Indicar que YNAB está correctamente conectado.
    YNAB_OK = True

except Exception as e:

    # Si ocurre algún problema al consultar YNAB,
    # no destruimos toda la aplicación inmediatamente.
    #
    # Mostramos el error en pantalla para poder diagnosticarlo.
    YNAB_OK = False

    contexto_ynab = None
    BUDGET_ID_ACTUAL = None
    PLAN_NOMBRE = None
    ACCOUNT_ID_ACTUAL = None
    CUENTA_NOMBRE = None

    st.error(
        f"No fue posible obtener la configuración actual de YNAB: {e}"
    )


# ============================================================
# TÍTULO DE LA APLICACIÓN
# ============================================================

st.title("Factura → YNAB")


# ============================================================
# INFORMACIÓN DEL PLAN Y LA CUENTA
# ============================================================

# >>> CORRECCIÓN
#
# Mostramos en el frontend exactamente dónde está
# trabajando la aplicación.
#
# Usamos "Plan" porque ese es el término que utiliza
# actualmente la interfaz de YNAB.
if YNAB_OK:

    st.info(
        f"**Plan:** {PLAN_NOMBRE} | "
        f"**Cuenta:** {CUENTA_NOMBRE}"
    )


# ============================================================
# BUSCAR FACTURAS EN GMAIL
# ============================================================

dias = st.number_input(
    "Buscar facturas de los últimos días",
    min_value=1,
    max_value=365,
    value=10
)


# ------------------------------------------------------------
# BOTÓN DE BÚSQUEDA
# ------------------------------------------------------------

if st.button("📬 Buscar facturas en Gmail"):

    # Conectarse a Gmail.
    service = conectar_gmail()

    # Buscar los adjuntos de los últimos días indicados.
    archivos = obtener_adjuntos(service, dias)

    # Guardar los archivos en la sesión para no perderlos
    # cuando Streamlit vuelva a ejecutar el script.
    st.session_state["gmail_archivos"] = archivos


# ============================================================
# MOSTRAR RESULTADOS DE GMAIL
# ============================================================

if "gmail_archivos" in st.session_state:

    # Recuperar los archivos guardados.
    archivos = st.session_state["gmail_archivos"]


    # --------------------------------------------------------
    # SI ENCONTRAMOS ARCHIVOS
    # --------------------------------------------------------

    if archivos:

        # Lista de opciones que mostraremos en el selectbox.
        opciones = []

        # Diccionario:
        #
        # texto mostrado → archivo original
        mapa_archivos = {}


        # ----------------------------------------------------
        # PROCESAR ADJUNTOS
        # ----------------------------------------------------

        for a in archivos:

            # Intentar extraer el XML del adjunto.
            xml_bytes = extraer_xml(a)


            # Si no hay XML, ignoramos ese archivo.
            if not xml_bytes:
                continue


            # Leer información de la factura.
            items, fecha, proveedor, total_factura = leer_factura(
                io.BytesIO(xml_bytes)
            )


            # Si no contiene productos, ignoramos la factura.
            if not items:
                continue


            # ------------------------------------------------
            # OBTENER TOTAL
            # ------------------------------------------------

            # Utilizar el total real de la factura si existe.
            if total_factura:

                total = total_factura

            else:

                # Si no existe, calcularlo sumando los productos.
                total = sum(
                    i["precio"]
                    for i in items
                )


            # Texto que aparecerá en el selector.
            label = (
                f"📄 {proveedor} — "
                f"${total:,.0f} — "
                f"{fecha}"
            )


            # Añadir la factura a las opciones.
            opciones.append(label)

            # Relacionar el texto con el archivo.
            mapa_archivos[label] = a


        # ----------------------------------------------------
        # MOSTRAR SELECTOR
        # ----------------------------------------------------

        if opciones:

            seleccion_gmail = st.selectbox(
                "Facturas encontradas en Gmail",
                opciones
            )


            # Recuperar el archivo seleccionado.
            archivo_dict = mapa_archivos[seleccion_gmail]


            # Extraer nuevamente el XML.
            xml_bytes = extraer_xml(archivo_dict)


            if xml_bytes:

                # Convertir bytes a archivo en memoria.
                archivo = io.BytesIO(xml_bytes)

            else:

                archivo = None


        else:

            st.info(
                "No se encontraron facturas válidas "
                "en los adjuntos."
            )

            archivo = None


    # --------------------------------------------------------
    # NO HAY ARCHIVOS
    # --------------------------------------------------------

    else:

        st.info(
            "No se encontraron correos con adjuntos."
        )

        archivo = None


# ------------------------------------------------------------
# SI NO HAY RESULTADOS DE GMAIL
# ------------------------------------------------------------

else:

    # Permitir subir manualmente un XML.
    archivo = st.file_uploader(
        "Sube factura XML"
    )


# ============================================================
# PROCESAR FACTURA
# ============================================================

# Solo ejecutamos el resto de la aplicación
# cuando tenemos una factura.
if archivo:


    # --------------------------------------------------------
    # LEER XML
    # --------------------------------------------------------

    # Extraer información estructurada.
    items, fecha, proveedor, total_factura = leer_factura(
        archivo
    )


    # ========================================================
    # INFORMACIÓN GENERAL
    # ========================================================

    st.write(
        "Fecha factura:",
        fecha
    )

    st.write(
        "Proveedor:",
        proveedor
    )


    # ========================================================
    # TOTAL DE LA FACTURA
    # ========================================================

    if total_factura:

        total = total_factura

    else:

        total = sum(
            i["precio"]
            for i in items
        )


    st.metric(
        "Total factura",
        f"${total:,.0f}"
    )


    # ========================================================
    # TRAER CATEGORÍAS DESDE YNAB
    # ========================================================

    # Obtener categorías del Plan actual.
    categorias = traer_categorias()


    # Crear mapa:
    #
    # nombre categoría → ID categoría
    mapa_cat = {
        c["nombre"]: c["id"]
        for c in categorias
    }


    # Obtener solamente los nombres.
    nombres_cat = list(
        mapa_cat.keys()
    )


    # ========================================================
    # TÍTULO DE ITEMS
    # ========================================================

    st.subheader(
        "Items detectados"
    )


    # Lista donde guardaremos las selecciones.
    seleccion = []


    # ========================================================
    # RECORRER PRODUCTOS
    # ========================================================

    for idx, i in enumerate(items):

        # Nombre del producto.
        producto = i["producto"]

        # Precio del producto.
        precio = i["precio"]


        # ----------------------------------------------------
        # BUSCAR MEMORIA EN MONGO
        # ----------------------------------------------------

        memoria = productos.find_one({
            "producto": producto
        })


        if memoria:

            # Si Mongo recuerda la categoría,
            # utilizarla como valor predeterminado.
            categoria_default = memoria["categoria"]

        else:

            # Si nunca hemos visto el producto,
            # utilizar la primera categoría disponible.
            categoria_default = nombres_cat[0]


        # ----------------------------------------------------
        # BLOQUE VISUAL
        # ----------------------------------------------------

        with st.container():

            col1, col2 = st.columns(
                [5, 1]
            )


            # ------------------------------------------------
            # COLUMNA IZQUIERDA
            # ------------------------------------------------

            with col1:

                # Mostrar producto.
                st.markdown(
                    f"**{producto}**"
                )


                # Selector de categoría.
                categoria = st.selectbox(
                    "Categoría",
                    nombres_cat,
                    index=(
                        nombres_cat.index(
                            categoria_default
                        )
                        if categoria_default in nombres_cat
                        else 0
                    ),
                    key=f"{producto}_{idx}"
                )


            # ------------------------------------------------
            # COLUMNA DERECHA
            # ------------------------------------------------

            with col2:

                # Mostrar precio.
                st.markdown(
                    f"### ${precio:,.0f}"
                )


        # Separador visual.
        st.divider()


        # ----------------------------------------------------
        # GUARDAR SELECCIÓN
        # ----------------------------------------------------

        seleccion.append({

            # Nombre del producto.
            "producto": producto,

            # Precio.
            "precio": precio,

            # Nombre de la categoría.
            "categoria": categoria,

            # ID de la categoría.
            "categoria_id": mapa_cat[categoria]
        })


    # ========================================================
    # BOTÓN PARA ENVIAR A YNAB
    # ========================================================

    if st.button(
        "🚀 Enviar factura a YNAB",
        use_container_width=True
    ):


        # ----------------------------------------------------
        # COMPROBAR YNAB
        # ----------------------------------------------------

        # >>> CORRECCIÓN
        #
        # Antes utilizábamos directamente:
        #
        #     ACCOUNT_ID
        #
        # proveniente de Secrets.
        #
        # Ahora utilizamos el ACCOUNT_ID que acabamos
        # de obtener desde YNAB.
        #
        # Esto garantiza que la cuenta pertenece al
        # Plan que acabamos de detectar.

        if not YNAB_OK:

            st.error(
                "No se puede enviar la factura porque "
                "no fue posible determinar el Plan "
                "y la cuenta actuales de YNAB."
            )

            st.stop()


        # ----------------------------------------------------
        # RECALCULAR CONTEXTO ANTES DE ESCRIBIR
        # ----------------------------------------------------

        # >>> CORRECCIÓN DE SEGURIDAD
        #
        # Volvemos a consultar YNAB justo antes de crear
        # las transacciones.
        #
        # Así, si cambió el Plan o la cuenta mientras
        # la aplicación estaba abierta, no utilizamos
        # información antigua.

        contexto_ynab = obtener_contexto_ynab()

        budget_id_actual = contexto_ynab["budget_id"]

        account_id_actual = contexto_ynab["account_id"]

        plan_nombre_actual = contexto_ynab["budget"]["name"]

        cuenta_nombre_actual = contexto_ynab["account"]["name"]


        # ----------------------------------------------------
        # CONFIRMACIÓN VISUAL
        # ----------------------------------------------------

        st.info(
            f"**Plan:** {plan_nombre_actual} | "
            f"**Cuenta:** {cuenta_nombre_actual}"
        )


        # ----------------------------------------------------
        # CREAR TRANSACCIONES
        # ----------------------------------------------------

        for s in seleccion:

            crear_transaccion(

                # >>> CORRECCIÓN
                #
                # Utilizamos el ACCOUNT_ID recién obtenido
                # desde YNAB.
                account_id_actual,

                # ID de categoría.
                s["categoria_id"],

                # Proveedor.
                proveedor,

                # Precio.
                s["precio"],

                # Fecha.
                fecha,

                # Producto.
                s["producto"]
            )


            # ------------------------------------------------
            # ACTUALIZAR MEMORIA MONGO
            # ------------------------------------------------

            productos.update_one(

                # Buscar por producto.
                {
                    "producto": s["producto"]
                },

                # Actualizar categoría.
                {
                    "$set": {
                        "categoria": s["categoria"],
                        "categoria_id": s["categoria_id"]
                    }
                },

                # Crear documento si no existe.
                upsert=True
            )


        # ----------------------------------------------------
        # CONFIRMACIÓN FINAL
        # ----------------------------------------------------

        st.success(
            "Factura enviada a YNAB"
        )