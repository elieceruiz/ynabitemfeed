# app.py

import streamlit as st
from parser_xml import leer_factura
from ynab_api import traer_categorias, crear_transaccion
from db import productos

ACCOUNT_ID = st.secrets["ACCOUNT_ID"]

st.title("Factura → YNAB")

archivo = st.file_uploader("Sube factura XML")

if archivo:

    items, fecha, proveedor = leer_factura(archivo)

    st.write("Fecha factura:", fecha)
    st.write("Proveedor:", proveedor)
    total = sum(i["precio"] for i in items)
    st.metric("Total factura", f"${total:,.0f}")

    categorias = traer_categorias()

    mapa_cat = {c["nombre"]: c["id"] for c in categorias}
    nombres_cat = list(mapa_cat.keys())

    st.subheader("Items detectados")

    seleccion = []

    for i in items:

        producto = i["producto"]
        precio = i["precio"]

        memoria = productos.find_one({"producto": producto})

        if memoria:
            categoria_default = memoria["categoria"]
        else:
            categoria_default = nombres_cat[0]


        
        with st.container():
        
            col1, col2 = st.columns([5,1])
        
            with col1:
        
                st.markdown(f"**{producto}**")
        
                categoria = st.selectbox(
                    "Categoría",
                    nombres_cat,
                    index=nombres_cat.index(categoria_default)
                    if categoria_default in nombres_cat else 0,
                    key=producto
                )
        
            with col2:
                st.markdown(f"### ${precio:,.0f}")
        
        st.divider()        

        
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
                proveedor,        # PAYEE real
                s["precio"],
                fecha,
                s["producto"]     # MEMO con el producto
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
