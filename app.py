# app.py

# ------------------------------------------
# IMPORTACIONES
# ------------------------------------------

# Streamlit es el framework que usamos para la interfaz web
import streamlit as st
import io

# Función que lee el XML de la factura electrónica
# y devuelve: items (productos), fecha y proveedor
from parser_xml import leer_factura

# Funciones para interactuar con la API de YNAB
from ynab_api import traer_categorias, crear_transaccion

# Colección Mongo donde guardamos memoria de productos → categoría
from db import productos

# NUEVO: Gmail
from gmail_fetch import conectar_gmail, obtener_adjuntos, extraer_xml


# ------------------------------------------
# CONFIGURACIÓN
# ------------------------------------------

# ID de la cuenta de YNAB donde se registrarán las transacciones
ACCOUNT_ID = st.secrets["ACCOUNT_ID"]


# ------------------------------------------
# TÍTULO DE LA APLICACIÓN
# ------------------------------------------

st.title("Factura → YNAB")


# ------------------------------------------
# BUSCAR FACTURAS EN GMAIL
# ------------------------------------------

dias = st.number_input(
    "Buscar facturas de los últimos días",
    min_value=1,
    max_value=365,
    value=120
)


if st.button("📬 Buscar facturas en Gmail"):

    service = conectar_gmail()

    archivos = obtener_adjuntos(service, dias)

    st.session_state["gmail_archivos"] = archivos


# Mostrar resultados Gmail si existen
if "gmail_archivos" in st.session_state:

    archivos = st.session_state["gmail_archivos"]

    if archivos:

        opciones = []
        mapa_archivos = {}

        for a in archivos:

            xml_bytes = extraer_xml(a)

            if not xml_bytes:
                continue

            items, fecha, proveedor = leer_factura(io.BytesIO(xml_bytes))

            if not items:
                continue

            total = sum(i["precio"] for i in items)

            # mejora visual agregando fecha
            label = f"📄 {proveedor} — ${total:,.0f} — {fecha}"

            opciones.append(label)
            mapa_archivos[label] = a

        if opciones:

            seleccion_gmail = st.selectbox(
                "Facturas encontradas en Gmail",
                opciones
            )

            archivo_dict = mapa_archivos[seleccion_gmail]

            xml_bytes = extraer_xml(archivo_dict)

            if xml_bytes:
                archivo = io.BytesIO(xml_bytes)
            else:
                archivo = None

        else:

            st.info("No se encontraron facturas válidas en los adjuntos.")
            archivo = None

    else:

        st.info("No se encontraron correos con adjuntos.")
        archivo = None

else:

    archivo = st.file_uploader("Sube factura XML")

# ------------------------------------------
# SOLO EJECUTAMOS EL RESTO SI HAY ARCHIVO
# ------------------------------------------

if archivo:

    # Leemos el XML y extraemos información estructurada
    # items = lista de productos
    # fecha = fecha de la factura
    # proveedor = comercio que emitió la factura
    items, fecha, proveedor = leer_factura(archivo)


    # ------------------------------------------
    # INFORMACIÓN GENERAL DE LA FACTURA
    # ------------------------------------------

    # Mostrar fecha de la factura
    st.write("Fecha factura:", fecha)

    # Mostrar proveedor / comercio
    st.write("Proveedor:", proveedor)


    # ------------------------------------------
    # TOTAL DE LA FACTURA
    # ------------------------------------------

    # Sumamos el precio de todos los items detectados
    total = sum(i["precio"] for i in items)

    # Mostramos el total como métrica visual
    st.metric("Total factura", f"${total:,.0f}")


    # ------------------------------------------
    # TRAER CATEGORÍAS DESDE YNAB
    # ------------------------------------------

    categorias = traer_categorias()

    mapa_cat = {c["nombre"]: c["id"] for c in categorias}

    nombres_cat = list(mapa_cat.keys())


    # ------------------------------------------
    # TÍTULO DE LA SECCIÓN DE ITEMS
    # ------------------------------------------

    st.subheader("Items detectados")


    # Lista donde guardaremos las selecciones del usuario
    seleccion = []


    # ------------------------------------------
    # RECORRER TODOS LOS PRODUCTOS DE LA FACTURA
    # ------------------------------------------

    for idx, i in enumerate(items):

        producto = i["producto"]
        precio = i["precio"]


        # ------------------------------------------
        # BUSCAR MEMORIA EN MONGO
        # ------------------------------------------

        memoria = productos.find_one({"producto": producto})

        if memoria:
            categoria_default = memoria["categoria"]
        else:
            categoria_default = nombres_cat[0]


        # ------------------------------------------
        # BLOQUE VISUAL DEL ITEM
        # ------------------------------------------

        with st.container():

            col1, col2 = st.columns([5,1])


            # ------------------------------------------
            # COLUMNA IZQUIERDA
            # ------------------------------------------

            with col1:

                st.markdown(f"**{producto}**")

                categoria = st.selectbox(
                    "Categoría",
                    nombres_cat,
                    index=nombres_cat.index(categoria_default)
                    if categoria_default in nombres_cat else 0,
                    key=f"{producto}_{idx}"
                )


            # ------------------------------------------
            # COLUMNA DERECHA
            # ------------------------------------------

            with col2:

                st.markdown(f"### ${precio:,.0f}")


        st.divider()


        # ------------------------------------------
        # GUARDAR SELECCIÓN DEL USUARIO
        # ------------------------------------------

        seleccion.append({
            "producto": producto,
            "precio": precio,
            "categoria": categoria,
            "categoria_id": mapa_cat[categoria]
        })


    # ------------------------------------------
    # BOTÓN PARA ENVIAR A YNAB
    # ------------------------------------------

    if st.button("🚀 Enviar factura a YNAB", use_container_width=True):

        for s in seleccion:

            crear_transaccion(
                ACCOUNT_ID,
                s["categoria_id"],
                proveedor,
                s["precio"],
                fecha,
                s["producto"]
            )

            productos.update_one(
                {"producto": s["producto"]},
                {"$set": {
                    "categoria": s["categoria"],
                    "categoria_id": s["categoria_id"]
                }},
                upsert=True
            )

        st.success("Factura enviada a YNAB")