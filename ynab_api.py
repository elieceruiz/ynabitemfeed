# ynab_api.py

import requests
import streamlit as st
from datetime import date

TOKEN = st.secrets["YNAB_TOKEN"]
BUDGET = st.secrets["BUDGET_ID"]

def traer_categorias():

    url = f"https://api.ynab.com/v1/budgets/{BUDGET}/categories"
    headers = {"Authorization": f"Bearer {TOKEN}"}

    r = requests.get(url, headers=headers).json()

    categorias = []

    for group in r["data"]["category_groups"]:

        for cat in group["categories"]:

            if not cat["deleted"]:

                categorias.append({
                    "nombre": f"{group['name']} → {cat['name']}",
                    "id": cat["id"]
                })

    return categorias

def crear_transaccion(account_id, categoria_id, payee, amount):

    url = f"https://api.ynab.com/v1/budgets/{BUDGET}/transactions"

    payload = {
        "transaction": {
            "account_id": account_id,
            "date": str("date": fecha),
            "amount": -int(amount * 1000),
            "payee_name": payee,
            "category_id": categoria_id
        }
    }

    headers = {"Authorization": f"Bearer {TOKEN}"}

    requests.post(url, json=payload, headers=headers)
