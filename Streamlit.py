# whatsapp_bulk_streamlit_enhanced.py
import os
import ssl
import asyncio
import aiohttp
from aiohttp import FormData, ClientConnectorError, ClientResponseError
from dotenv import load_dotenv
import pandas as pd
import streamlit as st
from typing import Optional, Callable, Dict, Any, List

load_dotenv()
TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
API_VERSION = os.getenv("API_VERSION", "v17.0")

if not TOKEN or not PHONE_NUMBER_ID:
    raise RuntimeError("WHATSAPP_TOKEN and PHONE_NUMBER_ID must be set in .env")

BASE_URL = f"https://graph.facebook.com/{API_VERSION}/{PHONE_NUMBER_ID}/messages"
MEDIA_UPLOAD_URL = f"https://graph.facebook.com/{API_VERSION}/{PHONE_NUMBER_ID}/media"
AUTH_HEADERS = {"Authorization": f"Bearer {TOKEN}"}

# Config
MAX_CONCURRENCY = 10
RETRIES = 3
INITIAL_BACKOFF = 1  # seconds

# --------------------------
# Helper functions
# --------------------------
def make_ssl_context():
    ctx = ssl.create_default_context()
    return ctx

async def upload_media_once(session: aiohttp.ClientSession, file_bytes: bytes, filename: str, mime_type: str) -> str:
    data = FormData()
    data.add_field("file", file_bytes, filename=filename, content_type=mime_type)
    data.add_field("messaging_product", "whatsapp")
    async with session.post(MEDIA_UPLOAD_URL, data=data, headers=AUTH_HEADERS) as resp:
        text = await resp.text()
        try:
            j = await resp.json()
        except Exception:
            raise RuntimeError(f"Media upload failed: status {resp.status} body: {text}")

        if resp.status not in (200, 201):
            raise RuntimeError(f"Media upload failed: {j}")

        media_id = j.get("id") or j.get("media", {}).get("id") or j.get("media_id")
        if not media_id:
            raise RuntimeError(f"No media id returned from upload: {j}")
        return media_id

async def safe_post(session: aiohttp.ClientSession, payload: Dict[str, Any], retries: int = RETRIES) -> Dict[str, Any]:
    backoff = INITIAL_BACKOFF
    for attempt in range(1, retries + 1):
        try:
            async with session.post(BASE_URL, headers={**AUTH_HEADERS, "Content-Type": "application/json"}, json=payload) as resp:
                try:
                    j = await resp.json()
                except Exception:
                    txt = await resp.text()
                    raise RuntimeError(f"Invalid JSON response ({resp.status}): {txt}")

                if 200 <= resp.status < 300:
                    return {"ok": True, "status": resp.status, "body": j}
                else:
                    return {"ok": False, "status": resp.status, "body": j}
        except (ClientConnectorError, ClientResponseError, asyncio.TimeoutError, RuntimeError) as e:
            if attempt == retries:
                return {"ok": False, "error": str(e)}
            await asyncio.sleep(backoff)
            backoff *= 2
        except Exception as e:
            return {"ok": False, "error": str(e)}
    return {"ok": False, "error": "exhausted retries"}

async def send_message_with_semaphore(session: aiohttp.ClientSession, semaphore: asyncio.Semaphore,
                                      payload: Dict[str, Any]) -> Dict[str, Any]:
    async with semaphore:
        return await safe_post(session, payload)

async def bulk_send(contacts: List[Dict[str, Any]],
                    message_template: str,
                    image_file_tuple: Optional[Dict[str, Any]],
                    pdf_file_tuple: Optional[Dict[str, Any]],
                    dry_run: bool = False,
                    progress_callback: Optional[Callable[[int, int], None]] = None
                    ) -> List[Dict[str, Any]]:
    ssl_ctx = make_ssl_context()
    connector = aiohttp.TCPConnector(ssl=ssl_ctx, limit_per_host=MAX_CONCURRENCY*2)
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    async with aiohttp.ClientSession(connector=connector) as session:
        image_media_id = None
        doc_media_id = None

        if image_file_tuple and not dry_run:
            try:
                image_media_id = await upload_media_once(session,
                                                        image_file_tuple["bytes"],
                                                        image_file_tuple["filename"],
                                                        image_file_tuple["mime"])
            except Exception as e:
                return [{"ok": False, "error": f"Image upload failed: {e}"}]

        if pdf_file_tuple and not dry_run:
            try:
                doc_media_id = await upload_media_once(session,
                                                      pdf_file_tuple["bytes"],
                                                      pdf_file_tuple["filename"],
                                                      pdf_file_tuple["mime"])
            except Exception as e:
                return [{"ok": False, "error": f"Document upload failed: {e}"}]

        coros = []
        total_messages = 0
        for contact in contacts:
            phone = str(contact["phone"])
            # Apply template replacements
            personalized_text = message_template.format(**contact)
            if personalized_text.strip():
                payload_text = {"messaging_product": "whatsapp", "to": phone, "type": "text", "text": {"body": personalized_text}}
                if dry_run:
                    coros.append(asyncio.sleep(0, result={"ok": True, "dry_run": True, "phone": phone, "type": "text"}))
                else:
                    coros.append(send_message_with_semaphore(session, semaphore, payload_text))
                total_messages += 1

            if image_media_id:
                payload_image = {"messaging_product": "whatsapp", "to": phone, "type": "image", "image": {"id": image_media_id}}
                if dry_run:
                    coros.append(asyncio.sleep(0, result={"ok": True, "dry_run": True, "phone": phone, "type": "image"}))
                else:
                    coros.append(send_message_with_semaphore(session, semaphore, payload_image))
                total_messages += 1

            if doc_media_id:
                payload_doc = {"messaging_product": "whatsapp", "to": phone, "type": "document",
                               "document": {"id": doc_media_id, "filename": pdf_file_tuple["filename"]}}
                if dry_run:
                    coros.append(asyncio.sleep(0, result={"ok": True, "dry_run": True, "phone": phone, "type": "document"}))
                else:
                    coros.append(send_message_with_semaphore(session, semaphore, payload_doc))
                total_messages += 1

        results = []
        completed = 0
        for fut in asyncio.as_completed(coros):
            try:
                res = await fut
            except Exception as e:
                res = {"ok": False, "error": str(e)}
            results.append(res)
            completed += 1
            if progress_callback:
                progress_callback(completed, total_messages)
        return results

# --------------------------
# Streamlit UI
# --------------------------
st.set_page_config(page_title="ESSERRI Brand Group", layout="wide")
st.title("ESSERRI Brand Group — Bulk WhatsApp Sender")

st.markdown("""
<style>
.stApp { background-color: #607D8B; color: black; }
</style>
""", unsafe_allow_html=True)

uploaded_file = st.file_uploader("Upload contacts CSV", type=["csv"])
message_template = st.text_area("Enter your message (use placeholders like {name})")
image_file = st.file_uploader("Upload an image (.jpg/.jpeg/.png)", type=["jpg","jpeg","png"])
pdf_file = st.file_uploader("Upload a PDF file", type=["pdf"])

dry_run = st.checkbox("Dry run mode (validate only, do not send)")

image_tuple = None
pdf_tuple = None
if image_file:
    image_tuple = {"bytes": image_file.read(), "filename": image_file.name, "mime": image_file.type or "image/jpeg"}
if pdf_file:
    pdf_tuple = {"bytes": pdf_file.read(), "filename": pdf_file.name, "mime": pdf_file.type or "application/pdf"}

if st.button("Send Messages") and uploaded_file:
    try:
        contacts_df = pd.read_csv(uploaded_file)
    except Exception as e:
        st.error(f"Failed to read CSV: {e}")
        st.stop()

    contacts_df.columns = contacts_df.columns.str.strip().str.lower()
    possible_cols = ["phone_number", "phone", "phone_no", "phone_nu",
                     "mobile", "number", "contact", "msisdn"]
    phone_col = None
    for col in possible_cols:
        if col in contacts_df.columns:
            phone_col = col
            break
    if phone_col is None:
        st.error(f"No valid phone column found. Columns: {contacts_df.columns.tolist()}")
        st.stop()

    contacts_df["phone"] = contacts_df[phone_col].astype(str).str.replace(r"[^0-9]", "", regex=True)
    contacts = contacts_df.to_dict("records")
    st.write(f"📱 Loaded {len(contacts)} contacts")

    progress_bar = st.progress(0)
    progress_text = st.empty()
    def progress_callback(completed, total):
        pct = int((completed/total)*100)
        progress_bar.progress(pct)
        progress_text.text(f"Processed {completed}/{total} messages ({pct}%)")

    results = asyncio.run(bulk_send(contacts, message_template, image_tuple, pdf_tuple, dry_run, progress_callback))

    # Logging CSV
    log_rows = []
    for i, r in enumerate(results):
        phone = contacts[i % len(contacts)]["phone"]  # approximate, works for text only
        if dry_run:
            status = "dry_run"
            message_id = ""
            error = ""
        else:
            status = "ok" if r.get("ok") else "fail"
            body = r.get("body", {})
            message_id = body.get("messages", [{}])[0].get("id", "") if body else ""
            error = r.get("error", "")
        log_rows.append({"phone_number": phone, "status": status, "message_id": message_id, "error": error})

    log_df = pd.DataFrame(log_rows)
    log_filename = f"whatsapp_log_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv"
    log_df.to_csv(log_filename, index=False)
    st.success(f"✅ Completed. Log saved to {log_filename}")
    st.download_button("Download log CSV", data=log_df.to_csv(index=False).encode(), file_name=log_filename)

    # Show first 20 responses
    st.json(results[:20])
