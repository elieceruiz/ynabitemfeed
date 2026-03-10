# db.py

from pymongo import MongoClient
import streamlit as st

client = MongoClient(st.secrets["MONGO_URI"])

db = client.facturas

productos = db.productos
