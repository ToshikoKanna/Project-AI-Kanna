import os
import geocoder
from groq import Groq
#import openai
import datetime
import winsound
import sys
import pytchat
import time
import re
import pyaudio
import keyboard
import wave
import threading
import json
import socket
import numpy as np
from emoji import demojize
from config import *
from utils.translate import *
from utils.TTS import *
from utils.subtitle import *
from utils.promptMaker import *
from utils.twitch_config import *
from tavily import TavilyClient
from google import genai
from google.genai import types
# to help the CLI write unicode characters to the terminal
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf8', buffering=1)

# API Keys & Client Setup
api_key = os.getenv("GEMINI_API_KEY")

# Kita tetap di v1beta (default), tapi kita ubah ID modelnya
client = genai.Client(api_key=api_key) 

# this is the gemini model that i use
model_id = "gemini-3-flash-preview"

tavily_api_key = "" # put your API key here
tavily = TavilyClient(api_key=tavily_api_key)
conversation = []
# Create a dictionary to hold the message data
history = {"history": conversation}

mode = 0
total_characters = 0
chat = ""
chat_now = ""
chat_prev = ""
is_Speaking = False
owner_name = "Samuel"
blacklist = ["Nightbot", "streamelements"]

# function to get the user's input audio

def record_audio():
    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 44100
    WAVE_OUTPUT_FILENAME = "input.wav"
    
    # --- COBA TURUNKAN THRESHOLD KE SANGAT RENDAH DULU ---
    THRESHOLD = 1000       
    SILENCE_LIMIT = 1.5    
    
    p = pyaudio.PyAudio()
    
    try:
        stream = p.open(format=FORMAT, 
                        channels=CHANNELS, 
                        rate=RATE, 
                        input=True, 
                        frames_per_buffer=CHUNK)
    except Exception as e:
        print(f"Gagal membuka Mic: {e}")
        p.terminate()
        return

    frames = []
    print("Listening... (Coba bicara sekarang)")

    recording_started = False
    silent_chunks = 0
    
    while True:
        try:
            # exception_on_overflow=False penting supaya tidak crash kalau laptop lag
            data = stream.read(CHUNK, exception_on_overflow=False)
            audio_data = np.frombuffer(data, dtype=np.int16)
            amplitude = np.abs(audio_data).mean() 

            # Tampilkan volume di terminal biar kita tahu mic nyala
            if amplitude > 10: 
                print(f"Volume: {int(amplitude)}", end='\r')

            if amplitude > THRESHOLD:
                if not recording_started:
                    print("\n[!] Suara masuk! Merekam...")
                    recording_started = True
                frames.append(data)
                silent_chunks = 0
            elif recording_started:
                frames.append(data)
                silent_chunks += 1
                if silent_chunks > int(SILENCE_LIMIT * RATE / CHUNK):
                    print("\nSelesai merekam.")
                    break
        except Exception:
            break

    stream.stop_stream()
    stream.close()
    p.terminate()

    if len(frames) > 0:
        wf = wave.open(WAVE_OUTPUT_FILENAME, 'wb')
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))
        wf.close()
        transcribe_audio("input.wav")
    else:
        print("Tidak ada suara yang terekam.")

# function to transcribe the user's audio
def transcribe_audio(file):
    global chat_now
    try:
        with open(file, "rb") as f:
            audio_data = f.read()
            
        response = client.models.generate_content(
            model=model_id,
            contents=[
                types.Part.from_bytes(data=audio_data, mime_type="audio/wav"),
                "Output ONLY the plain transcription text in Indonesian. No introductory phrases, no conversational filler, no bolding, no quotes. Just the spoken words."
            ]
        )
        
        # Membersihkan teks dari markdown (seperti **) dan kalimat pembuka otomatis
        raw_text = response.text.strip().replace("*", "")
        # Regex untuk membuang pola "Teks dari audio adalah: " dsb jika Gemini masih bandel
        clean_text = re.sub(r'^(Teks dari audio|Hasil|Transcription|Teks).*?[:\-]\s*', '', raw_text, flags=re.IGNORECASE)
        
        chat_now = clean_text
        if not chat_now:
            return

        print("Question: " + chat_now)
        
        conversation.append({'role': 'user', 'content': f"{owner_name} said {chat_now}"})
        openai_answer()
        
    except Exception as e:
        print(f"Error Transcribe: {e}")

    
    ##internet search
def search_internet(query):
    try:
        # Menghapus "Samuel said" agar hasil Google lebih akurat
        query_bersih = query.replace("Samuel said ", "")
        
        # do search without "print" word so not make the terminal full
        search_result = tavily.search(query=query_bersih, search_depth="basic", max_results=3)
        
        # Take content from the searching results
        context = "\n".join([f"{r['content']}" for r in search_result['results']])
        return context
    except Exception as e:
        return ""
    
    
    
    
    
    

# function to get an answer from OpenAI
def openai_answer():
    global total_characters, conversation
    user_input = conversation[-1]['content']

    # --- 1. SEARCH ALWAYS ON ---
    hasil_internet = search_internet(user_input)

    # --- 2. DATE, TIME & LOCATION ---
    now = datetime.datetime.now()
    konteks_natural = f"(Sekadar info: Sekarang {now.strftime('%A, %H:%M')}. Info internet: {hasil_internet})"

    # --- 3. MIX THE  PROMPT ---
    # Take identity from the identity.txt from promptMaker
    identity = getIdentity("characterConfig/Pina/identity.txt")
    
    # Take the history of last conversation (max 5 last messages so it can more have some space)
    history_chat = "\n".join([f"{m['role']}: {m['content']}" for m in conversation[-5:]])

    full_prompt = f"{identity}\n\nSejarah Chat:\n{history_chat}\n\nInfo Tambahan: {konteks_natural}\n\nSamuel: {user_input}\nKanna:"

    # --- 4. SEND TO GEMINI ---
    try:
        response = client.models.generate_content(
            model=model_id, 
            contents=full_prompt
        )
        message = response.text
    except Exception as e:
        print(f"Error Gemini: {e}")
        message = "sorry, there something error with my brain..."

    # --- 5. SAVE IN HISTORY ---
    conversation.append({'role': 'assistant', 'content': message})
    
    # --- 6. TRANSLATE & TTS ---
    translate_text(message)

    # --- 7. SAVE TO JSON ---
    # we wrap the 'conversation' into key of 'history' so the promptmaker would not gonna error
    with open("conversation.json", "w", encoding="utf-8") as f:
        json.dump({"history": conversation}, f, indent=4)

    # --- 8. CLEANUP ---
    #turn off the input user to keep the history clear
    conversation[-1]['content'] = message

# function to capture livechat from youtube
def yt_livechat(video_id):
        global chat

        live = pytchat.create(video_id=video_id)
        while live.is_alive():
        # while True:
            try:
                for c in live.get().sync_items():
                    # Ignore chat from the streamer and Nightbot, change this if you want to include the streamer's chat
                    if c.author.name in blacklist:
                        continue
                    # if not c.message.startswith("!") and c.message.startswith('#'):
                    if not c.message.startswith("!"):
                        # Remove emojis from the chat
                        chat_raw = re.sub(r':[^\s]+:', '', c.message)
                        chat_raw = chat_raw.replace('#', '')
                        # chat_author makes the chat look like this: "Nightbot: Hello". So the assistant can respond to the user's name
                        chat = c.author.name + ' berkata ' + chat_raw
                        print(chat)
                        
                    time.sleep(1)
            except Exception as e:
                print("Error receiving chat: {0}".format(e))

def twitch_livechat():
    global chat
    sock = socket.socket()

    sock.connect((server, port))

    sock.send(f"PASS {token}\n".encode('utf-8'))
    sock.send(f"NICK {nickname}\n".encode('utf-8'))
    sock.send(f"JOIN {channel}\n".encode('utf-8'))

    regex = r":(\w+)!\w+@\w+\.tmi\.twitch\.tv PRIVMSG #\w+ :(.+)"

    while True:
        try:
            resp = sock.recv(2048).decode('utf-8')

            if resp.startswith('PING'):
                    sock.send("PONG\n".encode('utf-8'))

            elif not user in resp:
                resp = demojize(resp)
                match = re.match(regex, resp)

                username = match.group(1)
                message = match.group(2)

                if username in blacklist:
                    continue
                
                chat = username + ' said ' + message
                print(chat)

        except Exception as e:
            print("Error receiving chat: {0}".format(e))

# translating is optional
def translate_text(text):
    global is_Speaking
    # subtitle will act as subtitle for the viewer
    # subtitle = translate_google(text, "ID")

    # tts will be the string to be converted to audio
    detect = detect_google(text)
    tts = translate_google(text, f"{detect}", "JA")
    # tts = translate_deeplx(text, f"{detect}", "JA")
    tts_en = translate_google(text, f"{detect}", "EN")
    
    try:
        # print("ID Answer: " + subtitle)
        print("JP Answer: " + tts)
        print("EN Answer: " + tts_en)
    except Exception as e:
        print("Error printing text: {0}".format(e))
        return

    # Choose between the available TTS engines
    # Japanese TTS
    voicevox_tts(tts)

    # Silero TTS, Silero TTS can generate English, Russian, French, Hindi, Spanish, German, etc. Uncomment the line below. Make sure the input is in that language
    #silero_tts(tts_en, "en", "v3_en", "en_21")

    # Generate Subtitle
    generate_subtitle(chat_now, text)

    time.sleep(1)

    # is_Speaking is used to prevent the assistant speaking more than one audio at a time
    is_Speaking = True
    winsound.PlaySound("test.wav", winsound.SND_FILENAME)
    is_Speaking = False

    # Clear the text files after the assistant has finished speaking
    time.sleep(1)
    with open ("output.txt", "w") as f:
        f.truncate(0)
    with open ("chat.txt", "w") as f:
        f.truncate(0)

def preparation():
    global conversation, chat_now, chat, chat_prev
    while True:
        # If the assistant is not speaking, and the chat is not empty, and the chat is not the same as the previous chat
        # then the assistant will answer the chat
        chat_now = chat
        if is_Speaking == False and chat_now != chat_prev:
            # Saving chat history
            conversation.append({'role': 'user', 'content': chat_now})
            chat_prev = chat_now
            openai_answer()
        time.sleep(1)

if __name__ == "__main__":
    try:
        mode = input("Mode (1-Mic, 2-Youtube Live, 3-Twitch Live): ")

        if mode == "1":
            print("--- Kanna Voice Activation Active ---")
            print("Talk")
            while True:
                # Kanna hanya merekam jika dia sedang tidak berbicara
                if not is_Speaking:
                    record_audio()
                else:
                    time.sleep(0.5) # Tunggu sebentar jika Kanna masih ngomong
            
        elif mode == "2":
            live_id = input("Livestream ID: ")
            t = threading.Thread(target=preparation, daemon=True)
            t.start()
            yt_livechat(live_id)

        elif mode == "3":
            print("Make sure to change utils/twitch_config.py")
            t = threading.Thread(target=preparation, daemon=True)
            t.start()
            twitch_livechat()

    except KeyboardInterrupt:
        print("\nProgram dihentikan oleh Samuel. Sampai jumpa!")
        sys.exit(0)
