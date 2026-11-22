"""Factura → YNAB: importa XML de facturas y clasifica sus productos."""
import io
import streamlit as st
from db import productos
from gmail_fetch import conectar_gmail, obtener_adjuntos, extraer_xml
from parser_xml import leer_factura
from ynab_api import obtener_contexto_ynab, traer_categorias, crear_transacciones

st.set_page_config(page_title="Factura → YNAB", page_icon="🧾", layout="centered")
st.title("Factura → YNAB")
st.caption("Clasifica los productos de tus facturas y envíalos a tu presupuesto.")

try:
    contexto = obtener_contexto_ynab()
    budget_id = contexto["budget_id"]
    budget_name = contexto["budget"]["name"]
    cuentas = contexto["accounts"]
except Exception as exc:
    st.error(f"No fue posible conectar con YNAB: {exc}")
    st.stop()

st.info(f"**Presupuesto:** {budget_name}")
cuenta_inicial = contexto["account"]["id"] if contexto["account"] else None
cuenta_ids = [a["id"] for a in cuentas]
cuenta_por_id = {a["id"]: a for a in cuentas}
if cuenta_inicial not in cuenta_ids:
    cuenta_inicial = cuenta_ids[0] if len(cuentas) == 1 else None

selected_id = st.selectbox(
    "Cuenta donde registrar los gastos",
    options=cuenta_ids,
    index=cuenta_ids.index(cuenta_inicial) if cuenta_inicial in cuenta_ids else None,
    format_func=lambda account_id: (
        f"{cuenta_por_id[account_id]['name']} · "
        f"{cuenta_por_id[account_id].get('type', 'Cuenta')}"
    ),
    placeholder="Selecciona una cuenta de YNAB",
    key="ynab_account_id",
)
if selected_id:
    st.caption(f"Cuenta seleccionada: **{cuenta_por_id[selected_id]['name']}**")

st.subheader("Buscar facturas")
dias = st.number_input("Buscar facturas de los últimos días",
                       min_value=1, max_value=365, value=10, step=1)
if st.button("📬 Buscar facturas en Gmail", use_container_width=True):
    try:
        with st.spinner("Buscando adjuntos en Gmail…"):
            service = conectar_gmail()
            st.session_state["gmail_archivos"] = obtener_adjuntos(service, int(dias))
        st.success(f"Se encontraron {len(st.session_state['gmail_archivos'])} adjuntos.")
    except Exception as exc:
        st.error(f"No se pudieron consultar los correos: {exc}")

gmail_files = st.session_state.get("gmail_archivos", [])
gmail_invoices = []
for attachment in gmail_files:
    xml_bytes = extraer_xml(attachment)
    if not xml_bytes:
        continue
    try:
        items, date, supplier, total = leer_factura(io.BytesIO(xml_bytes))
        if items and date and supplier:
            gmail_invoices.append({
                "label": f"{supplier} · ${total:,.0f}" if total is not None
                         else f"{supplier} · {date}",
                "filename": attachment.get("filename", "factura.xml"),
                "xml": xml_bytes, "items": items, "date": date,
                "supplier": supplier, "total": total,
            })
    except Exception:
        continue

source = st.radio("Origen de la factura",
                  ["Subir XML", "Seleccionar desde Gmail"], horizontal=True)
invoice = None
if source == "Subir XML":
    uploaded = st.file_uploader("Sube factura XML", type=["xml"])
    if uploaded is not None:
        try:
            parsed = leer_factura(uploaded)
            invoice = {"items": parsed[0], "date": parsed[1],
                       "supplier": parsed[2], "total": parsed[3]}
        except Exception as exc:
            st.error(f"No se pudo leer el XML: {exc}")
else:
    if gmail_invoices:
        labels = [f"{x['label']} · {x['date']} · {x['filename']}" for x in gmail_invoices]
        selected_index = st.selectbox(
            "Facturas encontradas en Gmail", range(len(gmail_invoices)),
            format_func=lambda i: labels[i],
        )
        invoice = gmail_invoices[selected_index]
    else:
        st.info("No hay facturas XML válidas en los resultados de Gmail. Ejecuta una búsqueda.")

if invoice and not invoice.get("items"):
    st.error("El XML se pudo abrir, pero no contiene líneas de productos válidas.")

if invoice and invoice.get("items"):
    items = invoice["items"]
    fecha = invoice["date"]
    proveedor = invoice["supplier"]
    total = invoice["total"]
    if total is None:
        total = sum(float(item.get("precio", 0)) for item in items)

    st.divider()
    st.subheader("Resumen de factura")
    col1, col2 = st.columns(2)
    col1.write(f"**Proveedor**\n{proveedor}")
    col2.write(f"**Fecha**\n{fecha}")
    st.metric("Total factura", f"${total:,.0f}")

    if not selected_id:
        st.warning("Selecciona una cuenta activa de YNAB antes de continuar.")
        st.stop()

    try:
        categorias = traer_categorias(budget_id)
    except Exception as exc:
        st.error(f"No se pudieron cargar las categorías de YNAB: {exc}")
        st.stop()
    if not categorias:
        st.error("El presupuesto no tiene categorías activas disponibles.")
        st.stop()

    category_names = [c["nombre"] for c in categorias]
    category_ids = {c["nombre"]: c["id"] for c in categorias}
    selections = []
    st.subheader("Productos detectados")

    for index, item in enumerate(items):
        product = str(item.get("producto") or "Producto sin descripción").strip()
        price = float(item.get("precio") or 0)
        try:
            memory = productos.find_one({"producto": product})
        except Exception:
            memory = None
            st.warning("No se pudo consultar la memoria de categorías en MongoDB.")
        remembered = memory.get("categoria") if memory else None
        default_index = category_names.index(remembered) if remembered in category_names else 0

        left, right = st.columns([5, 2])
        with left:
            st.markdown(f"**{product}**")
            category = st.selectbox("Categoría", category_names, index=default_index,
                                    key=f"category_{index}_{product}")
        with right:
            st.markdown(f"**${price:,.0f}**")
        selections.append({"producto": product, "precio": price,
                           "categoria": category, "category_id": category_ids[category]})

    st.divider()
    st.warning(
        f"Se crearán {len(selections)} transacciones en "
        f"**{budget_name} → {cuenta_por_id[selected_id]['name']}**. "
        "Revisa la factura y las categorías antes de enviar."
    )

    if st.button("🚀 Enviar factura a YNAB", type="primary", use_container_width=True):
        if not fecha:
            st.error("La factura no contiene una fecha válida; no se enviará.")
            st.stop()
        if not proveedor:
            st.error("No se pudo identificar el proveedor; no se enviará.")
            st.stop()
        rows = [{
            "category_id": item["category_id"], "proveedor": proveedor,
            "precio": item["precio"], "fecha": fecha, "producto": item["producto"],
        } for item in selections]
        try:
            with st.spinner("Registrando la factura en YNAB…"):
                created = crear_transacciones(budget_id, selected_id, rows)

            memory_errors = 0
            for item in selections:
                try:
                    productos.update_one(
                        {"producto": item["producto"]},
                        {"$set": {"categoria": item["categoria"],
                                  "categoria_id": item["category_id"]}},
                        upsert=True,
                    )
                except Exception:
                    memory_errors += 1

            st.success(f"Factura registrada: {len(created)} transacciones creadas en YNAB.")
            if memory_errors:
                st.warning(
                    f"YNAB recibió la factura, pero no se pudieron actualizar "
                    f"{memory_errors} recuerdos de categorías en MongoDB."
                )
        except Exception as exc:
            st.error(f"YNAB no confirmó el registro de la factura: {exc}")
            st.caption("No se actualizó la memoria de categorías. Revisa YNAB antes de reintentar para evitar duplicados.")
