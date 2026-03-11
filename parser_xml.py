# parser_xml.py

import xml.etree.ElementTree as ET


def leer_factura(xml_file):

    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
    except ET.ParseError:
        return [], None, None, None


    if "Invoice" in root.tag:
        invoice_root = root
    else:

        descripcion = None

        for node in root.findall(".//{*}Description"):
            texto = node.text
            if texto and "<Invoice" in texto:
                descripcion = texto
                break

        if not descripcion:
            return [], None, None, None

        descripcion = descripcion.strip()
        inicio = descripcion.find("<Invoice")

        if inicio == -1:
            return [], None, None, None

        descripcion = descripcion[inicio:]

        try:
            invoice_root = ET.fromstring(descripcion)
        except ET.ParseError:
            return [], None, None, None


    if invoice_root.find(".//{*}InvoiceLine") is None:
        return [], None, None, None


    fecha = None
    fecha_node = invoice_root.find(".//{*}IssueDate")

    if fecha_node is not None and fecha_node.text:
        fecha = fecha_node.text.strip()


    proveedor = "Proveedor desconocido"

    supplier_node = invoice_root.find(".//{*}AccountingSupplierParty//{*}RegistrationName")

    if supplier_node is None:
        supplier_node = invoice_root.find(".//{*}PartyName//{*}Name")

    if supplier_node is not None and supplier_node.text:
        proveedor = supplier_node.text.strip()


    items = []

    for line in invoice_root.findall(".//{*}InvoiceLine"):

        producto = line.find(".//{*}Description")
        cantidad = line.find(".//{*}InvoicedQuantity")

        nombre_producto = "UNKNOWN"

        if producto is not None and producto.text:
            nombre_producto = producto.text.strip()

        try:
            cantidad_valor = float(cantidad.text)
        except:
            cantidad_valor = 1


        precio_valor = 0

        # 1️⃣ POS supermercados (D1, Ara)
        precio_node = line.find(".//{*}Note[@languageLocaleID='linea1']")

        if precio_node is not None and precio_node.text:
            try:
                precio_valor = float(precio_node.text)
            except:
                precio_valor = 0

        else:

            # 2️⃣ subtotal línea DIAN
            subtotal_node = line.find(".//{*}LineExtensionAmount")

            if subtotal_node is not None and subtotal_node.text:

                try:
                    precio_valor = float(subtotal_node.text)
                except:
                    precio_valor = 0

                # sumar IVA si existe
                tax_node = line.find(".//{*}TaxAmount")

                if tax_node is not None and tax_node.text:
                    try:
                        precio_valor += float(tax_node.text)
                    except:
                        pass

            else:

                # 3️⃣ fallback
                precio_node = line.find(".//{*}PriceAmount")

                if precio_node is not None and precio_node.text:
                    try:
                        precio_valor = float(precio_node.text)
                    except:
                        precio_valor = 0


        items.append({
            "producto": nombre_producto,
            "precio": precio_valor,
            "cantidad": cantidad_valor
        })


    total_factura = None

    total_node = invoice_root.find(".//{*}PayableAmount")

    if total_node is not None and total_node.text:
        try:
            total_factura = float(total_node.text)
        except:
            total_factura = None


    return items, fecha, proveedor, total_factura