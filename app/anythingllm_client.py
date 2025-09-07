import requests
import os
from typing import Optional
from datetime import datetime

class AnythingLLMClient:
    def __init__(self):
        self.base_url = os.getenv("ANYTHINGLLM_URL", "http://localhost:3001")
        self.api_key = os.getenv("ANYTHINGLLM_API_KEY", "DEIN_API_KEY")
        self.workspace_slug = os.getenv("ANYTHINGLLM_WORKSPACE", "wago-edge-copilot")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        print(f"🔗 AnythingLLM Client initialisiert: {self.base_url}")
        print(f"📁 Workspace: {self.workspace_slug}")

    def test_connection(self) -> bool:
        """Testet die Verbindung zu AnythingLLM"""
        try:
            response = requests.get(f"{self.base_url}/api/ping", headers=self.headers, timeout=5)
            if response.status_code == 200:
                result = response.json()
                if result.get("online"):
                    print("✅ AnythingLLM-Verbindung erfolgreich getestet")
                    return True
            print(f"❌ AnythingLLM-Test fehlgeschlagen: {response.status_code}")
            return False
        except Exception as e:
            print(f"❌ AnythingLLM-Verbindungstest fehlgeschlagen: {e}")
            return False

    def send_machine_error(self, machine: str, code: str, description: str) -> Optional[dict]:
        """Sendet Maschinenfehler an AnythingLLM Workspace"""
        timestamp = datetime.now().isoformat()
        text = f"Maschine {machine}: Fehler {code} – {description} (Zeit: {timestamp})"
        
        # Verschiedene Upload-Methoden probieren
        upload_methods = [
            {
                "endpoint": f"/api/v1/workspace/{self.workspace_slug}/upload",
                "payload": {
                    "content": text,
                    "metadata": {
                        "source": "OPC UA",
                        "machine": machine,
                        "error_code": code,
                        "timestamp": timestamp
                    }
                }
            },
            {
                "endpoint": f"/api/v1/workspace/{self.workspace_slug}/documents",
                "payload": {
                    "text": text,
                    "source": "OPC UA"
                }
            },
            {
                "endpoint": f"/api/v1/workspace/{self.workspace_slug}/document/upload",
                "payload": {
                    "content": text,
                    "name": f"Fehler_{machine}_{code}_{timestamp[:10]}",
                    "metadata": {
                        "machine": machine,
                        "error_code": code
                    }
                }
            }
        ]
        
        for method in upload_methods:
            try:
                print(f"📤 Teste: {method['endpoint']}")
                response = requests.post(
                    f"{self.base_url}{method['endpoint']}",
                    headers=self.headers,
                    json=method['payload'],
                    timeout=10
                )
                
                print(f"   Status: {response.status_code}")
                print(f"   Response: {response.text[:200]}")
                
                if response.status_code in [200, 201]:
                    print(f"✅ Erfolgreich: {method['endpoint']}")
                    try:
                        return response.json()
                    except:
                        return {"success": True, "endpoint": method['endpoint']}
                        
            except Exception as e:
                print(f"   Fehler: {e}")
                continue
        
        print("❌ Alle Upload-Methoden fehlgeschlagen")
        return None

# Kompatibilitätsfunktion
def send_to_anythingllm(machine, code, description):
    client = AnythingLLMClient()
    return client.send_machine_error(machine, code, description)
