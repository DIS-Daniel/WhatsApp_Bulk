import streamlit as st
import pandas as pd
import aiohttp
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
API_VERSION = os.getenv("API_VERSION", "v17.0")

BASE_URL = f"https://graph.facebook.com/{API_VERSION}/{PHONE_NUMBER_ID}/messages"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

async def send_request(session, payload):
    async with session.post(BASE_URL, headers=HEADERS, json=payload) as response:
        return await response.json()

async def bulk_send(contacts, text, image_url, pdf_url, pdf_filename):
    async with aiohttp.ClientSession() as session:
        tasks = []
        for phone in contacts:
            if text:
                tasks.append(send_request(session, {
                    "messaging_product": "whatsapp",
                    "to": str(phone),
                    "type": "text",
                    "text": {"body": text}
                }))
            if image_url:
                tasks.append(send_request(session, {
                    "messaging_product": "whatsapp",
                    "to": str(phone),
                    "type": "image",
                    "image": {"link": image_url}
                }))
            if pdf_url and pdf_filename:
                tasks.append(send_request(session, {
                    "messaging_product": "whatsapp",
                    "to": str(phone),
                    "type": "document",
                    "document": {"link": pdf_url, "filename": pdf_filename}
                }))
        return await asyncio.gather(*tasks)

st.title("ESSERRI Brand Group")

uploaded_file = st.file_uploader("Upload contacts CSV", type=["csv"])
message_text = st.text_area("Enter your message")
image_url = st.text_input("Image URL (optional)")
pdf_url = st.text_input("PDF URL (optional)")
pdf_filename = st.text_input("PDF Filename (optional)")

if st.button("Send Messages"):
    if uploaded_file is not None:
        contacts_df = pd.read_csv(uploaded_file)
        contacts = contacts_df['phone_number'].tolist()
        st.write("Sending messages...")
        responses = asyncio.run(bulk_send(contacts, message_text, image_url, pdf_url, pdf_filename))
        st.write("Responses:", responses)
    else:
        st.error("Please upload a contacts CSV file.")