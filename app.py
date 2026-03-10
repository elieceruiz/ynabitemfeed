import streamlit as st
from parser_xml import leer_factura
from ynab_api import traer_categorias, crear_transaccion

st.title("Factura → YNAB")

archivo = st.file_uploader("Sube factura XML")

if archivo:

    items = leer_factura(archivo)

    st.subheader("Items detectados")

    for i in items:

        st.write(i["producto"], i["precio"])
