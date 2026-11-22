"""Conexión compartida a MongoDB para la memoria de productos."""
import streamlit as st
from pymongo import MongoClient

client = MongoClient(
    st.secrets["MONGO_URI"],
    connectTimeoutMS=5000,
    serverSelectionTimeoutMS=5000,
    socketTimeoutMS=10000,
    appname="ynabitemfeed",
)

db = client.facturas
productos = db.productos
