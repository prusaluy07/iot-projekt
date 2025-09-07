import requests
import os
from typing import Optional
from datetime import datetime
import json

class AnythingLLMClient:
    def __init__(self):
        self.base_url = os.getenv("ANYTHINGLLM_URL", "http://localhost:3001")
        self.api_key = os.getenv("ANYTHINGLLM_API_KEY", "DEIN_API_KEY")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        print(f"🔗 AnythingLLM Client initialisiert: {self.base_url}")
    
    def send_machine_error(self, machine: str, code: str, description: str) -> Optional[dict]:
        """Sendet Maschinenfehler an AnythingLLM"""
        timestamp = datetime.now().isoformat()
        text = f"Maschine {machine}: Fehler {code} – {description} (Zeit: {timestamp})"
        
        payload = {
            "content": text,
            "source": "OPC UA",
            "metadata": {
                "machine": machine,
                "error_code": code,
                "timestamp": timestamp,
                "type": "machine_error"
            }
        }
        
        try:
            print(f"📤 Sende an AnythingLLM: {machine} - {code}")
            response = requests.post(
                f"{self.base_url}/api/v1/documents",
                headers=self.headers,
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                print(f"✅ AnythingLLM: Fehler {code} von {machine} erfolgreich gesendet")
                return response.json()
            elif response.status_code == 401:
                print("❌ AnythingLLM: API-Key ungültig!")
                return None
            else:
                print(f"❌ AnythingLLM Error {response.status_code}: {response.text}")
                return None
                
        except requests.exceptions.ConnectionError:
            print("❌ Verbindung zu AnythingLLM fehlgeschlagen - Server erreichbar?")
            return None
        except requests.exceptions.Timeout:
            print("❌ Timeout bei AnythingLLM-Anfrage")
            return None
        except requests.exceptions.RequestException as e:
            print(f"❌ Verbindungsfehler zu AnythingLLM: {e}")
            return None

    def test_connection(self) -> bool:
        """Testet die Verbindung zu AnythingLLM"""
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/system/ping", 
                headers=self.headers,
                timeout=5
            )
            if response.status_code == 200:
                print("✅ AnythingLLM-Verbindung erfolgreich getestet")
                return True
            else:
                print(f"❌ AnythingLLM-Test fehlgeschlagen: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ AnythingLLM-Verbindungstest fehlgeschlagen: {e}")
            return False

# Ihre ursprüngliche Funktion (kompatibel)
def send_to_anythingllm(machine, code, description):
    """Kompatibilitätsfunktion für Ihren ursprünglichen Code"""
    client = AnythingLLMClient()
    return client.send_machine_error(machine, code, description)
