"""Factura → YNAB: interfaz minimalista para importar y clasificar facturas."""
import html
import io

import streamlit as st

from db import productos
from gmail_fetch import conectar_gmail, obtener_adjuntos, extraer_xml
from parser_xml import leer_factura
from ynab_api import obtener_contexto_ynab, traer_categorias, crear_transacciones


st.set_page_config(
    page_title="Factura → YNAB",
    page_icon="🧾",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    :root { --ink:#17231f; --muted:#748079; --line:#e7ece8; --soft:#f5f8f5; --green:#176b4b; --green-dark:#11543b; }
    .stApp { background:#fbfcfb; }
    [data-testid="stHeader"] { background:rgba(251,252,251,.92); }
    .block-container { max-width:760px; padding-top:2.1rem; padding-bottom:4rem; }
    h1,h2,h3,p,label { color:var(--ink); }
    h1 { letter-spacing:-.045em; font-weight:720; }
    h2,h3 { letter-spacing:-.025em; }
    [data-testid="stCaptionContainer"] p { color:var(--muted); }
    [data-testid="stMetric"] { background:var(--soft); border:1px solid var(--line); padding:1rem 1.1rem; border-radius:16px; }
    [data-testid="stMetricLabel"] p { color:var(--muted); }
    [data-testid="stMetricValue"] { color:var(--ink); letter-spacing:-.04em; }
    [data-testid="stVerticalBlockBorderWrapper"] { border-color:var(--line); border-radius:18px; background:#fff; }
    [data-testid="stFileUploader"] section { border:1px dashed #b9c9bf; border-radius:16px; background:#f8fbf8; }
    [data-testid="stFileUploader"] section small { color:var(--muted); }
    .stButton > button { border-radius:12px; min-height:2.8rem; font-weight:600; border-color:#dce5df; }
    .stButton > button[kind="primary"] { background:var(--green); border-color:var(--green); color:white; }
    .stButton > button[kind="primary"]:hover { background:var(--green-dark); border-color:var(--green-dark); }
    [data-baseweb="select"] > div,[data-testid="stNumberInput"] input { border-radius:12px; border-color:#dce5df; min-height:2.8rem; }
    [data-testid="stTabs"] [role="tab"] { font-weight:600; padding-top:.8rem; padding-bottom:.8rem; }
    [data-testid="stAlert"] { border-radius:14px; }
    .app-eyebrow,.step-label,.budget-label { color:var(--green); font-size:.72rem; font-weight:750; letter-spacing:.12em; text-transform:uppercase; margin-bottom:.35rem; }
    .app-subtitle { color:var(--muted); font-size:1rem; margin-top:-.35rem; }
    .budget-label { color:var(--muted); letter-spacing:.09em; }
    .budget-name { font-size:1.05rem; font-weight:650; color:var(--ink); }
    .product-name { font-weight:650; color:var(--ink); overflow-wrap:anywhere; }
    .product-price { font-weight:650; color:var(--ink); text-align:right; }
    div[data-testid="stExpander"] { border:1px solid var(--line); border-radius:14px; }
    @media (max-width:640px) {
      .block-container { padding:1.15rem 1rem 3rem; }
      h1 { font-size:2rem; }
      [data-testid="stMetric"] { padding:.8rem; }
      .stButton > button { width:100%; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="app-eyebrow">Control de gastos · Importación</div>', unsafe_allow_html=True)
st.title("Factura → YNAB")
st.markdown(
    '<p class="app-subtitle">De la factura a tu presupuesto, sin registrar cada producto a mano.</p>',
    unsafe_allow_html=True,
)

try:
    contexto = obtener_contexto_ynab()
    budget_id = contexto["budget_id"]
    budget_name = contexto["budget"]["name"]
    cuentas = contexto["accounts"]
except Exception as exc:
    st.error(f"No fue posible conectar con YNAB: {exc}")
    st.stop()

cuenta_ids = [account["id"] for account in cuentas]
cuenta_por_id = {account["id"]: account for account in cuentas}
cuenta_inicial = contexto["account"]["id"] if contexto["account"] else None
if cuenta_inicial not in cuenta_ids:
    cuenta_inicial = cuenta_ids[0] if len(cuentas) == 1 else None

with st.container(border=True):
    st.markdown('<div class="budget-label">Presupuesto conectado</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="budget-name">{html.escape(str(budget_name))}</div>', unsafe_allow_html=True)
    st.caption("Conexión activa con YNAB")

st.markdown('<div class="step-label">01 · Cuenta de destino</div>', unsafe_allow_html=True)
selected_id = st.selectbox(
    "¿En qué cuenta registrar los gastos?",
    options=cuenta_ids,
    index=cuenta_ids.index(cuenta_inicial) if cuenta_inicial in cuenta_ids else None,
    format_func=lambda account_id: (
        f"{cuenta_por_id[account_id]['name']} · "
        f"{cuenta_por_id[account_id].get('type', 'Cuenta')}"
    ),
    placeholder="Selecciona una cuenta de YNAB",
    key="ynab_account_id",
    label_visibility="collapsed",
)
if selected_id:
    st.caption(f"Los gastos se registrarán en **{cuenta_por_id[selected_id]['name']}**.")
else:
    st.caption("Selecciona una cuenta activa para continuar.")

st.markdown('<div class="step-label">02 · Añadir factura</div>', unsafe_allow_html=True)
source = st.radio(
    "Origen de la factura",
    ["Subir XML", "Buscar en Gmail"],
    horizontal=True,
    label_visibility="collapsed",
    key="invoice_source",
)
invoice = None

if source == "Subir XML":
    uploaded = st.file_uploader(
        "Selecciona el archivo XML de tu factura",
        type=["xml"],
        help="Se procesa para extraer proveedor, fecha, productos e importes.",
        label_visibility="collapsed",
    )
    if uploaded is not None:
        try:
            items, date, supplier, total = leer_factura(uploaded)
            invoice = {
                "items": items, "date": date, "supplier": supplier,
                "total": total, "filename": uploaded.name,
            }
        except Exception as exc:
            st.error(f"No se pudo leer el XML: {exc}")
else:
    with st.container(border=True):
        st.markdown("**Busca facturas recibidas por correo**")
        left, right = st.columns([1, 1.35], vertical_alignment="bottom")
        with left:
            dias = st.number_input("Antigüedad", min_value=1, max_value=365, value=10, step=1)
        with right:
            buscar = st.button("Buscar facturas", use_container_width=True)
        if buscar:
            try:
                with st.spinner("Consultando Gmail…"):
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
                    "label": f"{supplier} · ${total:,.0f}" if total is not None else f"{supplier} · {date}",
                    "filename": attachment.get("filename", "factura.xml"),
                    "items": items, "date": date, "supplier": supplier, "total": total,
                })
        except Exception:
            continue

    if gmail_invoices:
        labels = [
            f"{entry['label']} · {entry['date']} · {entry['filename']}"
            for entry in gmail_invoices
        ]
        selected_index = st.selectbox(
            "Facturas encontradas", range(len(gmail_invoices)),
            format_func=lambda index: labels[index], key="gmail_invoice_choice",
        )
        invoice = gmail_invoices[selected_index]
    elif st.session_state.get("gmail_archivos") is not None:
        st.info("No encontramos facturas XML válidas en esos adjuntos.")
    else:
        st.caption("La búsqueda utiliza acceso de solo lectura a Gmail.")

if invoice and not invoice.get("items"):
    st.warning("El archivo se abrió, pero no contiene líneas de productos válidas.")

if invoice and invoice.get("items"):
    items = invoice["items"]
    fecha = invoice["date"]
    proveedor = invoice["supplier"]
    total = invoice["total"]
    if total is None:
        total = sum(float(item.get("precio",0)) for item in items)

    st.markdown('<div class="step-label">03 · Revisar y clasificar</div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown(f"**{proveedor or 'Proveedor no identificado'}**")
        meta_left, meta_right = st.columns(2)
        meta_left.caption("FECHA")
        meta_left.write(fecha or "No identificada")
        meta_right.caption("ARCHIVO")
        meta_right.write(invoice.get("filename","Factura XML"))
        st.divider()
        st.metric("Total de la factura", f"${total:,.0f}")
        st.caption(f"{len(items)} productos detectados")

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

    category_names = [category["nombre"] for category in categorias]
    category_ids = {category["nombre"]:category["id"] for category in categorias}
    selections = []
    for index, item in enumerate(items):
        product = str(item.get("producto") or "Producto sin descripción").strip()
        price = float(item.get("precio") or 0)
        try:
            memory = productos.find_one({"producto":product})
        except Exception:
            memory = None
            st.warning("No se pudo consultar la memoria de categorías en MongoDB.")
        remembered = memory.get("categoria") if memory else None
        default_index = category_names.index(remembered) if remembered in category_names else 0

        with st.container(border=True):
            row_left, row_right = st.columns([4,1.35], vertical_alignment="center")
            with row_left:
                st.markdown(f'<div class="product-name">{html.escape(product)}</div>', unsafe_allow_html=True)
            with row_right:
                st.markdown(f'<div class="product-price">${price:,.0f}</div>', unsafe_allow_html=True)
            category = st.selectbox(
                "Categoría", category_names, index=default_index,
                key=f"category_{index}_{product}", label_visibility="collapsed",
            )
        selections.append({
            "producto":product, "precio":price, "categoria":category,
            "category_id":category_ids[category],
        })

    st.markdown('<div class="step-label">Confirmación</div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.write(
            f"Se crearán **{len(selections)} transacciones** en "
            f"**{budget_name} → {cuenta_por_id[selected_id]['name']}**."
        )
        st.caption("Comprueba los productos, importes y categorías antes de enviar.")

    if st.button("Enviar factura a YNAB", type="primary", use_container_width=True, disabled=not selections):
        if not fecha:
            st.error("La factura no contiene una fecha válida; no se enviará.")
            st.stop()
        if not proveedor:
            st.error("No se pudo identificar el proveedor; no se enviará.")
            st.stop()
        rows = [{
            "category_id":item["category_id"], "proveedor":proveedor,
            "precio":item["precio"], "fecha":fecha, "producto":item["producto"],
        } for item in selections]
        try:
            with st.spinner("Registrando la factura en YNAB…"):
                created = crear_transacciones(budget_id, selected_id, rows)
            memory_errors = 0
            for item in selections:
                try:
                    productos.update_one(
                        {"producto":item["producto"]},
                        {"$set":{"categoria":item["categoria"], "categoria_id":item["category_id"]}},
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
