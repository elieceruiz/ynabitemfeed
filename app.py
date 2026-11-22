"""Factura → YNAB: interfaz minimalista para importar y clasificar facturas."""
import html
import io

import streamlit as st

from db import productos
from gmail_fetch import conectar_gmail, obtener_adjuntos, extraer_xml
from parser_xml import leer_factura

# La app puede arrancar aunque Streamlit Cloud conserve temporalmente una
# copia anterior de parser_xml.py durante la sincronización del despliegue.
# La limpieza principal sigue en el parser; este fallback evita que una
# función auxiliar nueva impida cargar toda la interfaz.
try:
    from parser_xml import limpiar_descripcion_producto
except ImportError:
    import re

    def limpiar_descripcion_producto(descripcion):
        """Quita únicamente una frase final repetida, sin alterar el resto."""
        texto = str(descripcion or "").strip()

        while True:
            coincidencia = re.match(
                r"^(?P<prefijo>.*?)(?:\\s*[-–—]\\s*)(?P<repeticion>[^-–—]+)$",
                texto,
                flags=re.DOTALL,
            )
            if not coincidencia:
                break

            prefijo = coincidencia.group("prefijo").rstrip()
            repeticion = coincidencia.group("repeticion").strip()

            normalizado = " ".join(prefijo.split()).casefold()
            repetido = " ".join(repeticion.split()).casefold()

            if repetido and normalizado.endswith(repetido):
                texto = prefijo
            else:
                break

        return texto


from ynab_api import obtener_contexto_ynab, traer_categorias, crear_transacciones


# Configuración global de Streamlit: se mantiene centrada y sin barra lateral.
st.set_page_config(
    page_title="Factura → YNAB",
    page_icon="🧾",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    /*
     * 1. CONTROLES PROPIOS DE STREAMLIT
     * Se ocultan los elementos de navegación y administración que rodean
     * la aplicación. Esta técnica replica la solución que ya utilizábamos
     * en Faro 80 / Slave. No se oculta el contenido funcional de la app.
     */
    [data-testid="stSidebar"],
    [data-testid="collapsedControl"],
    [data-testid="stHeader"],
    [data-testid="stToolbar"],
    [data-testid="stDecoration"],
    [data-testid="stAppDeployButton"],
    #MainMenu,
    footer {
        display: none !important;
    }

    /*
     * 2. PALETA Y SUPERFICIE GENERAL
     * Las variables centralizan los colores para que futuros ajustes
     * visuales no obliguen a buscar y reemplazar valores repetidos.
     */
    :root {
        --ink: #17231f;
        --muted: #748079;
        --line: #e7ece8;
        --soft: #f5f8f5;
        --green: #176b4b;
        --green-dark: #11543b;
    }

    .stApp {
        background: #fbfcfb;
    }

    /*
     * 3. CONTENEDOR PRINCIPAL
     * En escritorio conserva un ancho de lectura cómodo.
     * El espacio superior móvil se define más abajo por separado para
     * evitar que el título quede debajo de la barra de estado del teléfono.
     */
    .block-container {
        max-width: 760px;
        padding-top: 2.1rem;
        padding-bottom: 4rem;
    }

    h1, h2, h3, p, label {
        color: var(--ink);
    }

    h1 {
        letter-spacing: -.045em;
        font-weight: 720;
    }

    h2, h3 {
        letter-spacing: -.025em;
    }

    [data-testid="stCaptionContainer"] p {
        color: var(--muted);
    }

    /*
     * 4. TARJETAS, MÉTRICAS Y CONTROLES
     * Se mantienen superficies blancas, bordes suaves y radios consistentes.
     * No se cambian los widgets ni su comportamiento; solo su presentación.
     */
    [data-testid="stMetric"] {
        background: var(--soft);
        border: 1px solid var(--line);
        padding: 1rem 1.1rem;
        border-radius: 16px;
    }

    [data-testid="stMetricLabel"] p {
        color: var(--muted);
    }

    [data-testid="stMetricValue"] {
        color: var(--ink);
        letter-spacing: -.04em;
    }

    [data-testid="stVerticalBlockBorderWrapper"] {
        border-color: var(--line);
        border-radius: 18px;
        background: #fff;
    }

    [data-testid="stFileUploader"] section {
        border: 1px dashed #b9c9bf;
        border-radius: 16px;
        background: #f8fbf8;
    }

    [data-testid="stFileUploader"] section small {
        color: var(--muted);
    }

    .stButton > button {
        border-radius: 12px;
        min-height: 2.8rem;
        font-weight: 600;
        border-color: #dce5df;
    }

    /*
     * El texto de algunos botones de Streamlit vive dentro de un <p>.
     * Como la regla global de párrafos define el color de texto, también
     * fijamos el blanco en los descendientes del botón primario para evitar
     * que esa regla global lo vuelva oscuro sobre el fondo verde.
     */
    .stButton > button[kind="primary"],
    .stButton > button[kind="primary"] * {
        background-color: var(--green);
        border-color: var(--green);
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff;
    }

    .stButton > button[kind="primary"]:hover,
    .stButton > button[kind="primary"]:hover * {
        background-color: var(--green-dark);
        border-color: var(--green-dark);
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff;
    }

    [data-baseweb="select"] > div,
    [data-testid="stNumberInput"] input {
        border-radius: 12px;
        border-color: #dce5df;
        min-height: 2.8rem;
    }

    [data-testid="stTabs"] [role="tab"] {
        font-weight: 600;
        padding-top: .8rem;
        padding-bottom: .8rem;
    }

    [data-testid="stAlert"] {
        border-radius: 14px;
    }

    /*
     * 5. TIPOGRAFÍA Y ETIQUETAS DE SECCIÓN
     * Estas clases se aplican a los pequeños rótulos y a los datos de factura.
     */
    .app-eyebrow,
    .step-label,
    .budget-label {
        color: var(--green);
        font-size: .72rem;
        font-weight: 750;
        letter-spacing: .12em;
        text-transform: uppercase;
        margin-bottom: .35rem;
    }

    .app-subtitle {
        color: var(--muted);
        font-size: 1rem;
        margin-top: -.35rem;
    }

    .budget-label {
        color: var(--muted);
        letter-spacing: .09em;
    }

    .budget-name {
        font-size: 1.05rem;
        font-weight: 650;
        color: var(--ink);
    }

    .product-name {
        font-weight: 650;
        color: var(--ink);
        overflow-wrap: anywhere;
    }

    .product-price {
        font-weight: 650;
        color: var(--ink);
        text-align: right;
    }

    div[data-testid="stExpander"] {
        border: 1px solid var(--line);
        border-radius: 14px;
    }

    /*
     * 6. PROTECCIÓN DE LA BARRA DE ESTADO EN MÓVILES
     *
     * El padding superior del contenedor solo separa el contenido al cargar
     * la página. No basta cuando el usuario desplaza el documento: el título
     * y otros elementos pueden pasar por detrás de los indicadores de Android.
     *
     * Para evitarlo, se crea una franja fija, opaca y no interactiva en la
     * parte superior del viewport. La franja permanece en su sitio durante
     * el scroll y tapa únicamente el área reservada a la barra del sistema.
     *
     * La variable CSS safe-area-inset-top aprovecha el área segura cuando el
     * navegador la expone. El mínimo de 56px sirve como respaldo para
     * navegadores Android que devuelven 0px o no implementan esa variable.
     *
     * El z-index mantiene la franja por encima del contenido de la app;
     * pointer-events:none permite que los toques sigan llegando a la página.
     */
    @media (max-width: 640px) {
        body::before {
            content: "";
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            height: max(56px, calc(env(safe-area-inset-top, 0px) + 32px));
            /*
             * Fondo verde oscuro para conservar el contraste con los
             * indicadores blancos de Android (hora, señal y batería).
             * No usar aquí el fondo claro de la aplicación: esta franja
             * ocupa también el área donde el sistema dibuja esos indicadores.
             */
            background: #11543b;
            z-index: 999999;
            pointer-events: none;
        }

        /*
         * Este espacio coloca el primer rótulo por debajo de la franja fija
         * cuando la página se abre. La franja, por separado, protege la zona
         * durante todo el desplazamiento.
         */
        .block-container {
            padding: 4.25rem 1rem 3rem;
        }

        h1 {
            font-size: 2rem;
        }

        [data-testid="stMetric"] {
            padding: .8rem;
        }

        .stButton > button {
            width: 100%;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# CABECERA: identidad y descripción breve de la herramienta.
st.markdown('<div class="app-eyebrow">Control de gastos · Importación</div>', unsafe_allow_html=True)
st.title("Factura → YNAB")
st.markdown(
    '<p class="app-subtitle">De la factura a tu presupuesto, sin registrar cada producto a mano.</p>',
    unsafe_allow_html=True,
)

# CONEXIÓN YNAB: recupera el presupuesto, sus cuentas y la cuenta sugerida.
# La selección se valida contra las cuentas activas devueltas por la API.
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

# PASO 1 — CUENTA: el usuario elige dónde registrar los gastos.
# Se conserva el ID real de la cuenta; el nombre solo se usa para mostrarla.
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

# PASO 2 — ORIGEN: permite trabajar desde un XML local o desde Gmail.
# Los dos caminos producen el mismo objeto `invoice` para reutilizar el flujo.
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

# PASO 3 — REVISIÓN: a partir de aquí ambos orígenes comparten el proceso.
# Se revisan los datos de cabecera, se clasifican productos y se confirma el envío.
if invoice and invoice.get("items"):
    items = invoice["items"]

    # Segunda barrera de normalización: los nombres se limpian justo antes
    # de mostrarlos, consultar la memoria de categorías y preparar el memo
    # de YNAB. Así también se corrigen facturas ya cargadas en el flujo de UI.
    for item in items:
        item["producto"] = limpiar_descripcion_producto(item.get("producto"))

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
        # Usa la forma gramatical correcta según la cantidad real de líneas.
        # Este contador describe las líneas extraídas, no productos agrupados.
        cantidad_productos = len(items)
        if cantidad_productos == 0:
            texto_productos = "No se detectaron productos"
        elif cantidad_productos == 1:
            texto_productos = "1 producto detectado"
        else:
            texto_productos = f"{cantidad_productos} productos detectados"
        st.caption(texto_productos)

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

    # Ajusta el verbo y el sustantivo según la cantidad real de transacciones.
    # El caso cero se expresa de forma explícita para no mostrar una promesa
    # de creación cuando todavía no hay productos seleccionados.
    cantidad_transacciones = len(selections)
    if cantidad_transacciones == 0:
        mensaje_confirmacion = "No se crearán transacciones en"
    elif cantidad_transacciones == 1:
        mensaje_confirmacion = "Se creará **1 transacción** en"
    else:
        mensaje_confirmacion = (
            f"Se crearán **{cantidad_transacciones} transacciones** en"
        )

    with st.container(border=True):
        st.write(
            f"{mensaje_confirmacion} "
            f"**{budget_name} → {cuenta_por_id[selected_id]['name']}**."
        )
        st.caption("Comprueba los productos, importes y categorías antes de enviar.")

    # ENVÍO: una única acción explícita del usuario crea las transacciones.
    # La memoria de categorías se actualiza después de la confirmación de YNAB.
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
