
import streamlit as st
import pandas as pd
import aiohttp
import asyncio
import os
from dotenv import load_dotenv
import base64

load_dotenv()
TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
API_VERSION = os.getenv("API_VERSION", "v17.0")

BASE_URL = f"https://graph.facebook.com/{API_VERSION}/{PHONE_NUMBER_ID}/messages"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

async def send_request(session, payload):
    async with session.post(BASE_URL, headers=HEADERS, json=payload) as response:
        return await response.json()

async def bulk_send(contacts, text, image_data, pdf_data):
    async with aiohttp.ClientSession() as session:
        tasks = []
        for phone in contacts:
            if text:
                tasks.append(send_request(session, {"messaging_product": "whatsapp", "to": str(phone), "type": "text", "text": {"body": text}}))
            if image_data:
                tasks.append(send_request(session, {"messaging_product": "whatsapp", "to": str(phone), "type": "image", "image": {"link": image_data}}))
            if pdf_data:
                tasks.append(send_request(session, {"messaging_product": "whatsapp", "to": str(phone), "type": "document", "document": {"link": pdf_data["url"], "filename": pdf_data["filename"]}}))
        return await asyncio.gather(*tasks)

# UI
st.set_page_config(page_title="ESSERRI Brand Group", layout="wide")
st.title("ESSERRI Brand Group")

# Force dark mode and background color

custom_css = """
<style>
.stApp {
    background-color: #607D8B;
    color: white;
}
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

uploaded_file = st.file_uploader("Upload contacts CSV", type=["csv"])
message_text = st.text_area("Enter your message")

# Drag and drop for image and PDF
image_file = st.file_uploader("Upload an image (.jpg or .png)", type=["jpg", "jpeg", "png"])
pdf_file = st.file_uploader("Upload a PDF file", type=["pdf"])

image_data = None
pdf_data = None

if image_file:
    image_bytes = image_file.read()
    image_base64 = base64.b64encode(image_bytes).decode()
    image_data = f"data:image/jpeg;base64,{image_base64}"

if pdf_file:
    pdf_filename = pdf_file.name
    pdf_bytes = pdf_file.read()
    pdf_base64 = base64.b64encode(pdf_bytes).decode()
    pdf_data = {"url": f"data:application/pdf;base64,{pdf_base64}", "filename": pdf_filename}

if st.button("Send Messages"):
    if uploaded_file is not None:
        contacts_df = pd.read_csv(uploaded_file)
        contacts = contacts_df['phone_number'].tolist()
        st.write("Sending messages...")
        responses = asyncio.run(bulk_send(contacts, message_text, image_data, pdf_data))
        st.write("Responses:", responses)
    else:
        st.error("Please upload a contacts CSV file.")
