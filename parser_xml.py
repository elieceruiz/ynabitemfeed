# parser_xml.py

import xml.etree.ElementTree as ET


def leer_factura(xml_file):

    # --------------------------------------
    # PARSEAR XML PRINCIPAL
    # --------------------------------------

    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
    except ET.ParseError:
        return [], None, None


    # --------------------------------------
    # SI YA ES UNA FACTURA (Invoice directo)
    # --------------------------------------

    if "Invoice" in root.tag:
        invoice_root = root

    else:

        # --------------------------------------
        # BUSCAR EL DESCRIPTION QUE CONTENGA LA FACTURA
        # --------------------------------------

        descripcion = None

        for node in root.findall(".//{*}Description"):

            texto = node.text

            if texto and "<Invoice" in texto:
                descripcion = texto
                break

        if not descripcion:
            return [], None, None


        # --------------------------------------
        # LIMPIAR CDATA
        # --------------------------------------

        descripcion = descripcion.strip()

        inicio = descripcion.find("<Invoice")

        if inicio == -1:
            return [], None, None

        descripcion = descripcion[inicio:]


        # --------------------------------------
        # PARSEAR FACTURA REAL
        # --------------------------------------

        try:
            invoice_root = ET.fromstring(descripcion)
        except ET.ParseError:
            return [], None, None


    # --------------------------------------
    # VERIFICAR QUE SEA FACTURA
    # --------------------------------------

    if invoice_root.find(".//{*}InvoiceLine") is None:
        return [], None, None


    # --------------------------------------
    # FECHA
    # --------------------------------------

    fecha = None

    fecha_node = invoice_root.find(".//{*}IssueDate")

    if fecha_node is not None and fecha_node.text:
        fecha = fecha_node.text.strip()


    # --------------------------------------
    # PROVEEDOR
    # --------------------------------------

    proveedor = "Proveedor desconocido"

    supplier_node = invoice_root.find(".//{*}AccountingSupplierParty//{*}RegistrationName")

    if supplier_node is None:
        supplier_node = invoice_root.find(".//{*}PartyName//{*}Name")

    if supplier_node is not None and supplier_node.text:
        proveedor = supplier_node.text.strip()


    # --------------------------------------
    # EXTRAER ITEMS
    # --------------------------------------

    items = []

    for line in invoice_root.findall(".//{*}InvoiceLine"):

        producto = line.find(".//{*}Description")
        precio = line.find(".//{*}PriceAmount")
        cantidad = line.find(".//{*}InvoicedQuantity")

        nombre_producto = "UNKNOWN"

        if producto is not None and producto.text:
            nombre_producto = producto.text.strip()


        try:
            precio_valor = float(precio.text)
        except:
            precio_valor = 0


        try:
            cantidad_valor = float(cantidad.text)
        except:
            cantidad_valor = 1


        items.append({
            "producto": nombre_producto,
            "precio": precio_valor,
            "cantidad": cantidad_valor
        })


    # --------------------------------------
    # RESULTADO FINAL
    # --------------------------------------

    return items, fecha, proveedor
