import requests
import json
import sys
from deep_translator import GoogleTranslator

# Memastikan terminal bisa menampilkan karakter Jepang/asing
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf8', buffering=1)

def translate_deeplx(text, source, target):
    url = "http://localhost:1188/translate"
    headers = {"Content-Type": "application/json"}
    params = {
        "text": text,
        "source_lang": source,
        "target_lang": target
    }
    try:
        payload = json.dumps(params)
        response = requests.post(url, headers=headers, data=payload)
        data = response.json()
        translated_text = data['data']
        return translated_text
    except:
        # Jika DeepLX mati, otomatis lempar ke Google Translate
        return translate_google(text, source, target)

def translate_google(text, source, target):
    try:
        # Menggunakan deep-translator sebagai pengganti googletrans yang error
        translated = GoogleTranslator(source='auto', target=target.lower()).translate(text)
        return translated
    except Exception as e:
        print(f"Error translate: {e}")
        return text
    
def detect_google(text):
    # Kita buat sederhana 'auto' supaya tidak perlu memanggil library deteksi yang berat
    return "ID"