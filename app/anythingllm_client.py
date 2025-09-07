import requests
import os
from typing import Optional
from datetime import datetime

class AnythingLLMClient:
    def __init__(self):
        self.base_url = os.getenv("ANYTHINGLLM_URL", "http://localhost:3001")
        self.embed_id = "1"
        self.embed_uuid = "68d8890d-7266-47f0-912f-672fc5c0afc7"
        print(f"🔗 AnythingLLM Embed-Widget initialisiert: {self.base_url}")
        print(f"🎯 Embed ID: {self.embed_id} | UUID: {self.embed_uuid}")

    def test_connection(self) -> bool:
        """Testet die Verbindung zu AnythingLLM"""
        try:
            response = requests.get(f"{self.base_url}/api/ping", timeout=5)
            if response.status_code == 200:
                result = response.json()
                if result.get("online"):
                    print("✅ AnythingLLM-Verbindung erfolgreich getestet")
                    return True
            return False
        except Exception as e:
            print(f"❌ AnythingLLM-Verbindungstest fehlgeschlagen: {e}")
            return False

    def send_machine_error(self, machine: str, code: str, description: str) -> Optional[dict]:
        """Sendet Maschinenfehler über Embed-Widget-Chat"""
        timestamp = datetime.now().isoformat()
        message = f"[Maschinenfehler] Maschine {machine}: Fehler {code} – {description} (Zeitstempel: {timestamp})"
        
        # Verschiedene Embed-Chat-Endpoints probieren
        chat_endpoints = [
            f"/api/v1/embed/{self.embed_id}/chat",
            f"/api/v1/embed/{self.embed_uuid}/chat", 
            f"/api/embed/{self.embed_id}/chat",
            f"/embed/{self.embed_id}/chat"
        ]
        
        for endpoint in chat_endpoints:
            try:
                print(f"📤 Teste Embed-Chat: {endpoint}")
                
                # Ohne API-Key probieren (öffentliches Widget)
                response = requests.post(
                    f"{self.base_url}{endpoint}",
                    headers={"Content-Type": "application/json"},
                    json={"message": message},
                    timeout=10
                )
                
                print(f"   Status: {response.status_code}")
                print(f"   Response: {response.text[:200]}")
                
                if response.status_code in [200, 201]:
                    print(f"✅ Embed-Chat erfolgreich: {endpoint}")
                    try:
                        return response.json()
                    except:
                        return {"success": True, "endpoint": endpoint, "method": "embed_chat"}
                        
            except Exception as e:
                print(f"   Fehler: {e}")
                continue
        
        print("❌ Alle Embed-Chat-Methoden fehlgeschlagen")
        return None

def send_to_anythingllm(machine, code, description):
    client = AnythingLLMClient()
    return client.send_machine_error(machine, code, description)
