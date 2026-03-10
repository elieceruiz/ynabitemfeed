# parser_xml.py

import xml.etree.ElementTree as ET

def leer_factura(xml_file):

    tree = ET.parse(xml_file)
    root = tree.getroot()

    # buscar la factura dentro del CDATA
    descripcion_node = root.find(".//{*}Description")

    if descripcion_node is None or descripcion_node.text is None:
        return [], None, None

    descripcion = descripcion_node.text
    
    if descripcion:
        
        # quitar espacios basura
        descripcion = descripcion.strip()
    
        # buscar inicio real del XML
        inicio = descripcion.find("<?xml")
    
        if inicio != -1:
            descripcion = descripcion[inicio:]
        else:
            # si no aparece <?xml, buscar <Invoice directamente
            inicio = descripcion.find("<Invoice")

            if inicio != -1:
                descripcion = descripcion[inicio:]
    
    # parsear la factura real
    try:
        invoice_root = ET.fromstring(descripcion)
    except ET.ParseError:
        # no es una factura válida
        return [], None, None
    
    # verificar que realmente tenga líneas de factura, que sea factura DIAN
    if invoice_root.find(".//{*}InvoiceLine") is None:
        return [], None, None

    # obtener fecha de la factura
    fecha_node = invoice_root.find(".//{*}IssueDate")
    fecha = fecha_node.text if fecha_node is not None else None

    # obtener proveedor (payee)
    supplier_node = invoice_root.find(".//{*}AccountingSupplierParty//{*}Name")
    proveedor = supplier_node.text.strip() if supplier_node is not None else "Proveedor desconocido"

    items = []

    for line in invoice_root.findall(".//{*}InvoiceLine"):

        producto = line.find(".//{*}Description")
        precio = line.find(".//{*}PriceAmount")
        cantidad = line.find(".//{*}InvoicedQuantity")

        items.append({
            "producto": producto.text.strip() if producto is not None else "UNKNOWN",
            "precio": float(precio.text) if precio is not None else 0,
            "cantidad": float(cantidad.text) if cantidad is not None else 1
        })

    return items, fecha, proveedor
