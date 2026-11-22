"""Cliente de la API de YNAB para Factura → YNAB.

La cuenta ya no se fija en el código: se resuelve por ID elegido en la
interfaz, por ACCOUNT_NAME (compatibilidad) o automáticamente si solo hay
una cuenta activa. Si hay varias, exige selección explícita.
"""
from decimal import Decimal, InvalidOperation

import requests
import streamlit as st

BASE_URL = "https://api.ynab.com/v1"
NOMBRE_FRESH_START = "fresh start"
ACCOUNT_NAME = ""  # Optional; loaded lazily so unit tests need no Streamlit Secrets.


def ynab_headers():
    return {"Authorization": f"Bearer {st.secrets['YNAB_TOKEN']}", "Content-Type": "application/json"}


def _get(path, params=None):
    response = requests.get(
        f"{BASE_URL}{path}", headers=ynab_headers(), params=params, timeout=20
    )
    response.raise_for_status()
    return response.json()["data"]


def _post(path, payload):
    response = requests.post(
        f"{BASE_URL}{path}", headers=ynab_headers(), json=payload, timeout=30
    )
    response.raise_for_status()
    return response.json()["data"]


def obtener_presupuestos():
    return _get("/budgets").get("budgets", [])


def obtener_budget_actual():
    coincidencias = [
        budget for budget in obtener_presupuestos()
        if NOMBRE_FRESH_START in budget.get("name", "").casefold()
    ]
    if not coincidencias:
        raise RuntimeError(
            "No se encontró un presupuesto cuyo nombre contenga "
            "'Fresh Start'. Revisa el nombre del presupuesto en YNAB."
        )
    coincidencias.sort(
        key=lambda item: item.get("last_modified_on") or "", reverse=True
    )
    return coincidencias[0]


def obtener_cuentas(budget_id):
    cuentas = _get(f"/budgets/{budget_id}/accounts").get("accounts", [])
    return [account for account in cuentas if not account.get("deleted", False)]


def resolver_cuenta(cuentas, account_id=None):
    """Resuelve una cuenta sin elegir silenciosamente entre varias."""
    if account_id:
        selected = next((a for a in cuentas if a["id"] == account_id), None)
        if selected is None:
            raise RuntimeError(
                "La cuenta seleccionada ya no está activa en este presupuesto. "
                "Selecciona una cuenta vigente."
            )
        return selected

    configured_name = ACCOUNT_NAME
    if not configured_name:
        try:
            configured_name = str(st.secrets.get("ACCOUNT_NAME", "") or "").strip()
        except Exception:
            configured_name = ""

    if configured_name:
        selected = next(
            (a for a in cuentas
             if a.get("name", "").strip().casefold() == configured_name.casefold()),
            None,
        )
        if selected:
            return selected
        # El nombre antiguo (por ejemplo, Pockets) ya no existe:
        # no bloqueamos la app; dejamos que el usuario elija otra cuenta.

    if len(cuentas) == 1:
        return cuentas[0]
    return None


def obtener_contexto_ynab(account_id=None):
    budget = obtener_budget_actual()
    accounts = obtener_cuentas(budget["id"])
    if not accounts:
        raise RuntimeError("El presupuesto Fresh Start no tiene cuentas activas.")
    account = resolver_cuenta(accounts, account_id=account_id)
    return {
        "budget": budget,
        "budget_id": budget["id"],
        "accounts": accounts,
        "account": account,
        "account_id": account["id"] if account else None,
    }


def traer_categorias(budget_id=None):
    if not budget_id:
        budget_id = obtener_budget_actual()["id"]
    groups = _get(f"/budgets/{budget_id}/categories").get("category_groups", [])
    result = []
    for group in groups:
        for category in group.get("categories", []):
            if not category.get("deleted", False) and not category.get("hidden", False):
                result.append({
                    "nombre": f"{group['name']} → {category['name']}",
                    "id": category["id"],
                })
    return result


def _a_milliunits(amount):
    try:
        value = Decimal(str(amount)) * Decimal("1000")
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Importe no válido: {amount!r}") from exc
    if value <= 0:
        raise ValueError("El importe de cada producto debe ser mayor que cero.")
    if value != value.to_integral_value():
        raise ValueError(f"El importe {amount!r} tiene más de tres decimales.")
    return -int(value)


def crear_transacciones(budget_id, account_id, rows):
    """Crea todos los items de una factura en una sola petición a YNAB."""
    if not budget_id or not account_id:
        raise ValueError("Falta seleccionar el presupuesto o la cuenta de YNAB.")
    if not rows:
        raise ValueError("La factura no contiene items para registrar.")

    accounts = obtener_cuentas(budget_id)
    if not any(a["id"] == account_id for a in accounts):
        raise RuntimeError("La cuenta seleccionada ya no pertenece al presupuesto.")

    payload_rows = []
    for row in rows:
        if not row.get("category_id"):
            raise ValueError(f"El producto {row.get('producto', '')} no tiene categoría.")
        payload_rows.append({
            "account_id": account_id,
            "date": row["fecha"],
            "amount": _a_milliunits(row["precio"]),
            "payee_name": row["proveedor"],
            "memo": row["producto"],
            "category_id": row["category_id"],
            "cleared": "cleared",
        })

    data = _post(
        f"/budgets/{budget_id}/transactions",
        {"transactions": payload_rows},
    )
    return data.get("transactions", [])


def crear_transaccion(account_id, categoria_id, payee, amount, fecha, memo):
    """Compatibilidad con la interfaz anterior."""
    context = obtener_contexto_ynab(account_id=account_id)
    created = crear_transacciones(
        context["budget_id"],
        account_id,
        [{
            "category_id": categoria_id,
            "proveedor": payee,
            "precio": amount,
            "fecha": fecha,
            "producto": memo,
        }],
    )
    return {"data": {"transaction": created[0] if created else None}}
