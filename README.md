# Factura → YNAB

Aplicación Streamlit para leer facturas XML desde archivos o Gmail, clasificar sus productos y registrar los gastos en YNAB. La memoria producto → categoría se conserva en MongoDB Atlas.

## Configuración en Streamlit Secrets

~~~toml
YNAB_TOKEN = "..."
MONGO_URI = "mongodb+srv://..."

GOOGLE_REFRESH_TOKEN = "..."
GOOGLE_CLIENT_ID = "..."
GOOGLE_CLIENT_SECRET = "..."

# Opcional: nombre de una cuenta activa para preseleccionarla.
# Si el nombre ya no existe, la aplicación permite elegir otra.
# Si solo hay una cuenta activa, se selecciona automáticamente.
ACCOUNT_NAME = "Nombre de una cuenta vigente"
~~~

ACCOUNT_NAME ya no es obligatorio. Si hay varias cuentas activas y el nombre configurado no coincide, la aplicación muestra un selector. No se guarda un ACCOUNT_ID fijo: los IDs se consultan en tiempo real desde el presupuesto Fresh Start.

## Comportamiento

1. Detecta el presupuesto cuyo nombre contiene Fresh Start.
2. Recupera las cuentas activas del presupuesto.
3. Selecciona automáticamente la cuenta configurada o la única disponible; si hay varias, exige selección explícita.
4. Lee XML subidos o adjuntos XML/ZIP de Gmail.
5. Obtiene las categorías activas del presupuesto detectado.
6. Permite clasificar cada producto y recuerda las elecciones en MongoDB.
7. Envía los productos de una factura mediante una sola petición de creación múltiple a YNAB.
8. Actualiza la memoria de categorías solo después de que YNAB confirma la operación.

## Seguridad y operación

- Gmail usa exclusivamente el permiso gmail.readonly.
- Los tokens y URI permanecen en Streamlit Secrets; no deben incluirse en Git.
- La aplicación no cambia el presupuesto, las cuentas ni las categorías de YNAB.
- Antes de reintentar una operación cuyo resultado quedó incierto por un timeout, revisa las transacciones en YNAB para evitar duplicados.
- Los cambios de esta rama no se despliegan automáticamente desde aquí. Revisa y prueba antes de integrar en main.
