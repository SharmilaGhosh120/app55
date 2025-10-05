# app.py
"""
Assessli Prototype — Streamlit app (single-file)
Features:
- Registration & consent
- Profile storage in SQLite
- Technical info capture (best-effort via external IP service)
- Mock "LBM" personalization and chat simulator
- Optional OpenAI LLM pass-through (if user supplies key) - disabled by default
- Admin view to inspect DB (local only)
Notes:
- This is a prototype/demo. Do NOT upload sensitive genomic/PHI data here.
"""

import streamlit as st
import sqlite3
import hashlib
import time
import json
from datetime import datetime
from typing import Optional, Dict, Any
import requests
import uuid
import html

# ---------------------------
# Configuration
# ---------------------------
DB_PATH = "assessli.db"
APP_TITLE = "Assessli — AI Companion Prototype (LBM demo)"
IPIFY_URL = "https://api.ipify.org?format=json"  # best-effort public IP lookup

# ---------------------------
# Utilities
# ---------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cur = conn.cursor()
    # Users table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            name TEXT,
            email TEXT,
            phone TEXT,
            meta JSON,
            created_at TEXT
        )
        """
    )
    # Conversations table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            role TEXT,
            message TEXT,
            metadata JSON,
            ts TEXT
        )
        """
    )
    conn.commit()
    return conn

def hash_text(x: str) -> str:
    return hashlib.sha256(x.encode("utf-8")).hexdigest()

def save_user(conn, user: Dict[str, Any]):
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO users (id, name, email, phone, meta, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user["id"], user["name"], user["email"], user["phone"], json.dumps(user.get("meta", {})), user["created_at"]),
    )
    conn.commit()

def save_message(conn, conv: Dict[str, Any]):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO conversations (id, user_id, role, message, metadata, ts) VALUES (?, ?, ?, ?, ?, ?)",
        (conv["id"], conv["user_id"], conv["role"], conv["message"], json.dumps(conv.get("metadata", {})), conv["ts"]),
    )
    conn.commit()

def fetch_user(conn, user_id: str) -> Optional[Dict[str, Any]]:
    cur = conn.cursor()
    cur.execute("SELECT id, name, email, phone, meta, created_at FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "name": row[1],
        "email": row[2],
        "phone": row[3],
        "meta": json.loads(row[4]) if row[4] else {},
        "created_at": row[5],
    }

def list_users(conn):
    cur = conn.cursor()
    cur.execute("SELECT id, name, email, phone, meta, created_at FROM users ORDER BY created_at DESC")
    rows = cur.fetchall()
    return [
        {
            "id": r[0],
            "name": r[1],
            "email": r[2],
            "phone": r[3],
            "meta": json.loads(r[4]) if r[4] else {},
            "created_at": r[5],
        }
        for r in rows
    ]

def try_get_public_ip():
    try:
        resp = requests.get(IPIFY_URL, timeout=3)
        if resp.status_code == 200:
            return resp.json().get("ip")
    except Exception:
        return None

# ---------------------------
# Mock LBM (simulator)
# ---------------------------
def mock_lbm_response(user_profile: Dict[str, Any], prompt: str) -> str:
    """
    A deterministic, explainable mock 'LBM' response generator.
    It uses user_profile fields to personalize replies.
    For real deployment, replace this with a secure call to the real LBM infra.
    """
    name = user_profile.get("name") or "Friend"
    # Basic personalization signals
    short_profile = user_profile.get("meta", {}).get("bio", "")
    # Build reply
    reply_lines = []
    reply_lines.append(f"Hi {name}, thanks for sharing that.")
    if short_profile:
        reply_lines.append(f"I remember you said: \"{short_profile}\" — I'll keep that in mind.")
    reply_lines.append("Here's a thoughtful reply to your message:")
    # Echo prompt-summary with gentle personalization
    sanitized = html.escape(prompt.strip())[:1000]
    reply_lines.append(f"> {sanitized}")
    # Add an adaptive suggestion
    reply_lines.append("Suggestion: try breaking the task into smaller steps. Which step would you like help with first?")
    # Add a short "confidence" indicator (mock)
    reply_lines.append("(This is a demo response from Assessli's prototype LBM — not medical or legal advice.)")
    return "\n\n".join(reply_lines)

# ---------------------------
# Streamlit UI pieces
# ---------------------------
def header():
    st.set_page_config(page_title=APP_TITLE, layout="centered")
    st.title(APP_TITLE)
    st.markdown(
        """
        **Prototype / Demo** — shows how Assessli might build an AI Companion experience.
        This demo **does not** store or process genomic/PHI data. See Privacy & Consent below.
        """
    )

def privacy_and_consent():
    st.header("Privacy & Consent")
    st.markdown(
        """
        **What we collect (demo):**
        - Basic profile fields you choose to provide (name, email, phone).
        - Technical info: public IP (best-effort), browser (optional).
        - Conversation logs (local SQLite) to demo personalization flows.

        **How we use the data (demo):**
        - Create your local account in this demo.
        - Personalize chat replies in the demo (mock LBM).
        - We will **not** sell your data. This demo stores data locally in `assessli.db`.

        **Do not upload sensitive genomic / health data** to this demo. If you need to process such data in production, consult compliance & legal teams.

        By using this demo you consent to local storage of the demo data for the purposes described above.
        """
    )

def register_flow(conn):
    st.subheader("Create your demo account")
    with st.form("register", clear_on_submit=False):
        name = st.text_input("Full name")
        email = st.text_input("Email")
        phone = st.text_input("Phone (optional)")
        bio = st.text_area("Short bio / what you'd like the Companion to remember (optional)", max_chars=800)
        allow_cookies = st.checkbox("I consent to demo cookies/tech-info capture (public IP lookup).", value=True)
        reject_sensitive = st.checkbox("I confirm I will NOT upload genomic or other sensitive health data.", value=True)
        submitted = st.form_submit_button("Create Demo Account")
    if submitted:
        if not name or not email:
            st.error("Please provide at minimum your name and email.")
            return None
        user_id = str(uuid.uuid4())
        created_at = datetime.utcnow().isoformat()
        meta = {"bio": bio, "allow_tech_info": bool(allow_cookies), "sensitive_data_ack": bool(reject_sensitive)}
        user = {"id": user_id, "name": name, "email": email, "phone": phone, "meta": meta, "created_at": created_at}
        save_user(conn, user)
        st.success("Account created — your demo user id: " + user_id)
        st.session_state["user_id"] = user_id
        return user
    return None

def detect_tech_info():
    st.write("Detecting technical info (best-effort)...")
    ip = try_get_public_ip()
    browser = None
    # Best-effort browser detection via user-agent placeholder:
    # In many Streamlit hosting contexts, server-side cannot read client UA. We provide an optional field for the browser UA.
    browser = st.text_input("Browser user-agent (paste if you want auto-detection)", value="")
    return {"ip": ip, "browser": browser}

def companion_chat_ui(conn, user):
    st.header("Assessli AI Companion (Demo)")
    st.markdown("Use the box below to send messages to your demo Companion. The Companion uses a **mock LBM** that personalizes replies using your profile info. Optionally, provide an OpenAI API key to use real LLMs (costs may apply).")

    # Optional: OpenAI key input for users who want to proxy to real LLMs
    st.info("If you'd like the app to call an LLM (OpenAI) instead of the mock LBM, paste your OpenAI API key below. It will only be used for this session and not stored.")
    openai_key = st.text_input("OpenAI API key (optional)", type="password")

    # Chatbox
    with st.form("chat_form", clear_on_submit=False):
        prompt = st.text_area("Message to Companion", height=150)
        remember_pref = st.checkbox("Save this message in your conversation log", value=True)
        submit = st.form_submit_button("Send")
    if submit and prompt:
        # assemble metadata
        tech = detect_tech_info() if user.get("meta", {}).get("allow_tech_info", True) else {}
        conv = {
            "id": str(uuid.uuid4()),
            "user_id": user["id"],
            "role": "user",
            "message": prompt,
            "metadata": {"tech": tech},
            "ts": datetime.utcnow().isoformat(),
        }
        if remember_pref:
            save_message(conn, conv)

        # If user provided an OpenAI key, optionally call the API (pass-through)
        if openai_key:
            st.info("Calling OpenAI (pass-through). Ensure you understand costs and provide your key securely.")
            # Minimal safe call — do not store the key. If network blocked, fallback to mock.
            try:
                headers = {"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"}
                payload = {
                    "model": "gpt-3.5-turbo",
                    "messages": [
                        {"role": "system", "content": "You are Assessli Companion. Keep replies concise and helpful."},
                        {"role": "user", "content": f"User profile: {json.dumps(user.get('meta', {}))}\n\nUser message: {prompt}"}
                    ],
                    "max_tokens": 300,
                    "temperature": 0.7
                }
                r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=12)
                if r.status_code == 200:
                    resp = r.json()
                    assistant_text = resp["choices"][0]["message"]["content"].strip()
                else:
                    st.warning("OpenAI call failed — falling back to mock LBM. (Status: %s)" % r.status_code)
                    assistant_text = mock_lbm_response(user, prompt)
            except Exception as e:
                st.warning("OpenAI call error: %s — using mock LBM." % str(e))
                assistant_text = mock_lbm_response(user, prompt)
        else:
            assistant_text = mock_lbm_response(user, prompt)

        # Save assistant message
        assistant_conv = {
            "id": str(uuid.uuid4()),
            "user_id": user["id"],
            "role": "assistant",
            "message": assistant_text,
            "metadata": {"generated_by": "mock_lbm" if not openai_key else "openai_proxy"},
            "ts": datetime.utcnow().isoformat(),
        }
        save_message(conn, assistant_conv)

        # Show assistant message
        st.markdown("**Assessli Companion:**")
        st.write(assistant_text)

def admin_panel(conn):
    st.sidebar.header("Admin")
    if st.sidebar.button("Show users (local DB)"):
        users = list_users(conn)
        st.sidebar.write(f"{len(users)} users")
        for u in users:
            st.sidebar.markdown(f"- **{u['name']}** — {u['email']} — created {u['created_at']}")
    if st.sidebar.button("Show recent conversations"):
        cur = conn.cursor()
        cur.execute("SELECT id, user_id, role, message, metadata, ts FROM conversations ORDER BY ts DESC LIMIT 50")
        rows = cur.fetchall()
        st.subheader("Recent Conversations (local)")
        for r in rows:
            st.markdown(f"**{r[2].upper()}** (user: {r[1]}) — {r[5]}")
            st.write(r[3])
            # small metadata preview
            try:
                md = json.loads(r[4]) if r[4] else {}
                st.caption(json.dumps(md))
            except Exception:
                pass
            st.write("---")

# ---------------------------
# App main
# ---------------------------
def main():
    conn = init_db()
    header()
    privacy_and_consent()

    # Session user
    st.sidebar.title("Quick actions")
    if "user_id" not in st.session_state:
        st.session_state["user_id"] = None

    # Register or load
    if not st.session_state["user_id"]:
        user = register_flow(conn)
        if user:
            st.success("Welcome, %s! Use the Companion tab below to chat." % user["name"])
    else:
        user = fetch_user(conn, st.session_state["user_id"])
        if not user:
            st.warning("Saved user not found — please create a new demo account.")
            st.session_state["user_id"] = None
            user = None

    # Tabs
    tabs = st.tabs(["Companion", "My Profile", "Admin"])
    with tabs[0]:
        if not user:
            st.info("Create or load a demo account to try the Companion.")
        else:
            companion_chat_ui(conn, user)

    with tabs[1]:
        st.header("My Profile (local)")
        if user:
            st.write("**Name:**", user["name"])
            st.write("**Email:**", user["email"])
            st.write("**Phone:**", user["phone"])
            st.write("**Bio (remembered):**", user["meta"].get("bio", ""))
            if st.button("Log out of demo account"):
                st.session_state["user_id"] = None
                st.experimental_rerun()
        else:
            st.info("No profile loaded. Create an account first.")

    with tabs[2]:
        st.header("Admin (local demo)")
        st.markdown("This admin view is local-only for demo/testing. Data is stored in `assessli.db` in this folder.")
        admin_panel(conn)

    st.sidebar.markdown("---")
    st.sidebar.caption("Demo created for prototyping. Do not upload sensitive genomic or PHI data here.")

if __name__ == "__main__":
    main()
