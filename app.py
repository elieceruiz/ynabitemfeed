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

if st.button("📬 Buscar facturas en Gmail"):

    service = conectar_gmail()

    archivos = obtener_adjuntos(service)

    st.session_state["gmail_archivos"] = archivos


# Mostrar resultados Gmail si existen
if "gmail_archivos" in st.session_state:

    archivos = st.session_state["gmail_archivos"]

    if archivos:

        nombres = [a["filename"] for a in archivos]

        seleccion_gmail = st.selectbox(
            "Facturas encontradas en Gmail",
            nombres
        )

        archivo_dict = next(
            a for a in archivos if a["filename"] == seleccion_gmail
        )

        xml_bytes = extraer_xml(archivo_dict)

        if xml_bytes:
            archivo = io.BytesIO(xml_bytes)

        else:
            archivo = None

    else:
        st.info("No se encontraron facturas en Gmail")
        archivo = None

else:

    # ------------------------------------------
    # SUBIDA DEL ARCHIVO XML
    # ------------------------------------------

    # Widget que permite subir la factura electrónica
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

    # Consultamos la API de YNAB para traer todas las categorías
    categorias = traer_categorias()


    # Convertimos la lista en un diccionario
    # "nombre_categoria" → "id_categoria"
    mapa_cat = {c["nombre"]: c["id"] for c in categorias}


    # Lista de nombres que usaremos en el dropdown
    nombres_cat = list(mapa_cat.keys())


    # ------------------------------------------
    # TÍTULO DE LA SECCIÓN DE ITEMS
    # ------------------------------------------

    st.subheader("Items detectados")


    # Lista donde guardaremos las selecciones del usuario
    # (producto, precio, categoría elegida)
    seleccion = []


    # ------------------------------------------
    # RECORRER TODOS LOS PRODUCTOS DE LA FACTURA
    # ------------------------------------------

    for i in items:

        # Nombre del producto detectado en el XML
        producto = i["producto"]

        # Precio del producto
        precio = i["precio"]


        # ------------------------------------------
        # BUSCAR MEMORIA EN MONGO
        # ------------------------------------------

        # Revisamos si este producto ya fue clasificado antes
        memoria = productos.find_one({"producto": producto})

        if memoria:
            # Si existe, usamos esa categoría por defecto
            categoria_default = memoria["categoria"]
        else:
            # Si no existe, usamos la primera categoría de la lista
            categoria_default = nombres_cat[0]


        # ------------------------------------------
        # BLOQUE VISUAL DEL ITEM
        # ------------------------------------------

        # Creamos un contenedor visual
        with st.container():

            # Dividimos el layout en dos columnas
            # izquierda = producto + categoría
            # derecha = precio
            col1, col2 = st.columns([5,1])


            # ------------------------------------------
            # COLUMNA IZQUIERDA
            # ------------------------------------------

            with col1:

                # Mostrar nombre del producto
                st.markdown(f"**{producto}**")

                # Dropdown para seleccionar categoría
                categoria = st.selectbox(
                    "Categoría",
                    nombres_cat,

                    # Usamos la categoría recordada si existe
                    index=nombres_cat.index(categoria_default)
                    if categoria_default in nombres_cat else 0,

                    # key evita conflictos entre dropdowns
                    key=producto
                )


            # ------------------------------------------
            # COLUMNA DERECHA
            # ------------------------------------------

            with col2:

                # Mostrar precio del item
                st.markdown(f"### ${precio:,.0f}")


        # Línea divisoria visual entre productos
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

        # Recorremos todos los items seleccionados
        for s in seleccion:

            # Creamos una transacción en YNAB
            crear_transaccion(
                ACCOUNT_ID,
                s["categoria_id"],
                proveedor,        # PAYEE (comercio)
                s["precio"],
                fecha,
                s["producto"]     # MEMO (producto)
            )


            # ------------------------------------------
            # GUARDAR MEMORIA EN MONGO
            # ------------------------------------------

            productos.update_one(
                {"producto": s["producto"]},

                {"$set": {
                    "categoria": s["categoria"],
                    "categoria_id": s["categoria_id"]
                }},

                # Si no existe el producto, lo crea
                upsert=True
            )


        # Mensaje de confirmación
        st.success("Factura enviada a YNAB")
