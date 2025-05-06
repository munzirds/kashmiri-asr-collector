import streamlit as st
import sqlite3
import hashlib
import os
from pathlib import Path
import base64
import streamlit.components.v1 as components

# Database setup
def init_db():
    conn = sqlite3.connect('asr_data.db')
    c = conn.cursor()
    
    # Create users table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE,
                  password_hash TEXT)''')
    
    # Create audio samples table
    c.execute('''CREATE TABLE IF NOT EXISTS audio_samples
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  filename TEXT,
                  text TEXT,
                  contributor_id INTEGER,
                  status TEXT DEFAULT 'unverified',
                  created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    
    conn.commit()
    conn.close()

init_db()

# Authentication functions
def make_password_hash(password):
    return hashlib.sha256(password.encode()).hexdigest()

def create_user(username, password):
    conn = sqlite3.connect('asr_data.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                  (username, make_password_hash(password)))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def verify_login(username, password):
    conn = sqlite3.connect('asr_data.db')
    c = conn.cursor()
    c.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
    result = c.fetchone()
    conn.close()
    if result:
        return result[0] == make_password_hash(password)
    return False

# Audio file management
AUDIO_UPLOAD_DIR = Path("user_uploads")
AUDIO_UPLOAD_DIR.mkdir(exist_ok=True)

def save_uploaded_audio(uploaded_file, contributor_id):
    file_ext = uploaded_file.name.split('.')[-1]
    filename = f"{contributor_id}_{hash(uploaded_file)}_{len(os.listdir(AUDIO_UPLOAD_DIR))}.{file_ext}"
    file_path = AUDIO_UPLOAD_DIR / filename
    
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    return str(file_path)

def save_recorded_audio(audio_data, contributor_id):
    # Decode base64 audio data
    audio_bytes = base64.b64decode(audio_data.split(',')[1])
    filename = f"{contributor_id}_recorded_{len(os.listdir(AUDIO_UPLOAD_DIR))}.wav"
    file_path = AUDIO_UPLOAD_DIR / filename
    
    with open(file_path, "wb") as f:
        f.write(audio_bytes)
    
    return str(file_path)

# JavaScript for audio recording
RECORDING_HTML = """
<script>
    let mediaRecorder;
    let audioChunks = [];
    
    function startRecording() {
        navigator.mediaDevices.getUserMedia({ audio: true })
            .then(stream => {
                mediaRecorder = new MediaRecorder(stream);
                mediaRecorder.start();
                
                audioChunks = [];
                mediaRecorder.addEventListener("dataavailable", event => {
                    audioChunks.push(event.data);
                });
                
                document.getElementById("status").innerText = "Recording...";
                document.getElementById("start-btn").disabled = true;
                document.getElementById("stop-btn").disabled = false;
            });
    }
    
    function stopRecording() {
        mediaRecorder.stop();
        mediaRecorder.addEventListener("stop", () => {
            const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
            const reader = new FileReader();
            reader.readAsDataURL(audioBlob);
            reader.onloadend = () => {
                const audioBase64 = reader.result;
                window.parent.postMessage({ type: 'AUDIO_DATA', data: audioBase64 }, '*');
            };
            document.getElementById("status").innerText = "Recording stopped";
            document.getElementById("start-btn").disabled = false;
            document.getElementById("stop-btn").disabled = true;
        });
    }
</script>
<div>
    <button id="start-btn" onclick="startRecording()">Start Recording</button>
    <button id="stop-btn" onclick="stopRecording()" disabled>Stop Recording</button>
    <p id="status">Press "Start Recording" to begin.</p>
</div>
"""

# App components
def login_page():
    st.title("Kashmiri ASR Data Collection - Login")
    
    choice = st.radio("Select Option", ["Login", "Register"])
    
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    
    if choice == "Login":
        if st.button("Login"):
            if verify_login(username, password):
                st.session_state.logged_in = True
                st.session_state.username = username
                st.rerun()
            else:
                st.error("Invalid credentials")
    else:
        if st.button("Register"):
            if create_user(username, password):
                st.success("Registration successful! Please login.")
            else:
                st.error("Username already exists")

def main_app():
    st.title(f"Kashmiri ASR Data Collection - Welcome {st.session_state.username}")
    
    # Get user ID
    conn = sqlite3.connect('asr_data.db')
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username = ?", (st.session_state.username,))
    user_id = c.fetchone()[0]
    conn.close()
    
    app_mode = st.sidebar.selectbox("Select Task", ["Label Existing Audio", "Contribute New Audio"])
    
    if app_mode == "Label Existing Audio":
        st.header("Label Existing Audio Clips")
        
        conn = sqlite3.connect('asr_data.db')
        c = conn.cursor()
        c.execute('''SELECT id, filename FROM audio_samples 
                     WHERE status = 'unverified' LIMIT 1''')
        audio_file = c.fetchone()
        conn.close()
        
        if audio_file:
            st.audio(audio_file[1])
            transcription = st.text_area("Transcribe the audio (Kashmiri)", key="transcription")
            
            if st.button("Submit Transcription"):
                conn = sqlite3.connect('asr_data.db')
                c = conn.cursor()
                c.execute('''UPDATE audio_samples 
                             SET text = ?, status = 'pending_verification'
                             WHERE id = ?''', (transcription, audio_file[0]))
                conn.commit()
                conn.close()
                st.success("Thank you for your contribution! The transcription will be verified.")
        else:
            st.info("No audio clips available for labeling at the moment. Check back later!")
    
    elif app_mode == "Contribute New Audio":
        st.header("Contribute New Audio and Text")
        
        upload_option = st.radio("Choose input method", ["Upload Audio File", "Record Audio"])
        
        audio_path = None
        if upload_option == "Upload Audio File":
            uploaded_audio = st.file_uploader("Upload Audio File", type=['wav', 'mp3'])
            if uploaded_audio:
                audio_path = save_uploaded_audio(uploaded_audio, user_id)
                st.audio(audio_path)
        
        elif upload_option == "Record Audio":
            st.write("Record your audio below:")
            components.html(RECORDING_HTML, height=150)
            
            # Handle recorded audio
            if 'audio_data' not in st.session_state:
                st.session_state.audio_data = None
                
            # Streamlit doesn't directly handle JS messages, so we use a workaround
            recorded_audio = st.text_input("Hidden input for audio data", key="audio_data_input", value="", style={"display": "none"})
            
            if recorded_audio:
                try:
                    audio_path = save_recorded_audio(recorded_audio, user_id)
                    st.session_state.audio_data = audio_path
                    st.audio(audio_path)
                except Exception as e:
                    st.error(f"Error saving recorded audio: {e}")
        
        transcription = st.text_area("Enter corresponding text in Kashmiri (ASR Label)", key="new_transcription")
        
        if st.button("Submit Contribution"):
            if audio_path and transcription:
                # Save to database
                conn = sqlite3.connect('asr_data.db')
                c = conn.cursor()
                c.execute('''INSERT INTO audio_samples 
                             (filename, text, contributor_id)
                             VALUES (?, ?, ?)''',
                          (audio_path, transcription, user_id))
                conn.commit()
                conn.close()
                st.success("Thank you for your contribution!")
                # Clear session state
                st.session_state.audio_data = None
            else:
                st.error("Please provide both audio and text")
    
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()

# Main app flow
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if st.session_state.logged_in:
    main_app()
else:
    login_page()
