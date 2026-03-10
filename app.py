import streamlit as st
from parser_xml import leer_factura
from ynab_api import traer_categorias, crear_transaccion
from db import productos

ACCOUNT_ID = st.secrets["ACCOUNT_ID"]

st.title("Factura → YNAB")

archivo = st.file_uploader("Sube factura XML")

if archivo:

    items = leer_factura(archivo)

    categorias = traer_categorias()

    mapa_cat = {c["nombre"]: c["id"] for c in categorias}

    st.subheader("Items detectados")

    seleccion = []

    for i in items:

        producto = i["producto"]
        precio = i["precio"]

        memoria = productos.find_one({"producto": producto})

        if memoria:
            categoria_default = memoria["categoria"]
        else:
            categoria_default = list(mapa_cat.keys())[0]

        categoria = st.selectbox(
            producto,
            mapa_cat.keys(),
            index=list(mapa_cat.keys()).index(categoria_default)
            if categoria_default in mapa_cat else 0
        )

        seleccion.append({
            "producto": producto,
            "precio": precio,
            "categoria": categoria,
            "categoria_id": mapa_cat[categoria]
        })

    if st.button("Enviar factura a YNAB"):

        for s in seleccion:

            crear_transaccion(
                ACCOUNT_ID,
                s["categoria_id"],
                s["producto"],
                s["precio"]
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
