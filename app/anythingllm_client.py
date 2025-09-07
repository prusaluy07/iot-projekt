import requests
import os
import json
from typing import Optional
from datetime import datetime
import re

class AnythingLLMClient:
    def __init__(self):
        self.base_url = os.getenv("ANYTHINGLLM_URL", "http://localhost:3001")
        self.api_key = os.getenv("ANYTHINGLLM_API_KEY", "DEIN_API_KEY")
        self.widget_uuid = "68d8890d-7266-47f0-912f-672fc5c0afc7"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        print(f"AnythingLLM Client initialisiert: {self.base_url}")

    def _is_html_response(self, response_text: str) -> bool:
        """Prüft ob die Antwort HTML ist"""
        return (
            response_text.strip().startswith('<!DOCTYPE html>') or
            response_text.strip().startswith('<html') or
            '<title>' in response_text or
            'AnythingLLM | Wago PLC Copilot' in response_text
        )

    def _handle_html_response(self, endpoint: str, response_text: str) -> dict:
        """Behandelt HTML-Antworten"""
        print(f"HTML-Antwort von {endpoint} erkannt - API nicht verfügbar")
        return {
            "success": False,
            "error": "API_NOT_AVAILABLE",
            "endpoint": endpoint,
            "response_type": "HTML",
            "message": "AnythingLLM-API gibt HTML zurück statt JSON"
        }

    def test_connection(self) -> bool:
        """Testet die Verbindung zu AnythingLLM"""
        try:
            response = requests.get(f"{self.base_url}/api/ping", timeout=5)
            if response.status_code == 200:
                response_text = response.text
                
                if self._is_html_response(response_text):
                    print("AnythingLLM-API gibt HTML zurück - Web-Interface aktiv, API nicht verfügbar")
                    return False
                
                try:
                    result = response.json()
                    if result.get("online"):
                        print("AnythingLLM-API-Verbindung erfolgreich getestet")
                        return True
                except json.JSONDecodeError:
                    print("AnythingLLM-Antwort ist kein gültiges JSON")
                    return False
            
            print(f"AnythingLLM-Test fehlgeschlagen: Status {response.status_code}")
            return False
            
        except Exception as e:
            print(f"AnythingLLM-Verbindungstest fehlgeschlagen: {e}")
            return False

    def _try_api_upload(self, message: str) -> Optional[dict]:
        """Versucht verschiedene API-Endpoints für Upload"""
        endpoints = [
            f"/api/v1/embed/{self.widget_uuid}/chat",
            f"/api/embed/{self.widget_uuid}/chat",
            "/api/v1/documents",
            f"/api/v1/workspace/1/chat",
            f"/api/v1/workspace/2/chat"
        ]
        
        payloads = [
            {"message": message},
            {"message": message, "sessionId": "iot-bridge-session"},
            {"message": message, "stream": False},
            {"content": message, "source": "OPC UA"}
        ]
        
        for endpoint in endpoints:
            for payload in payloads:
                try:
                    response = requests.post(
                        f"{self.base_url}{endpoint}",
                        headers=self.headers,
                        json=payload,
                        timeout=10
                    )
                    
                    response_text = response.text
                    
                    if self._is_html_response(response_text):
                        continue  # HTML-Antwort, nächsten Endpoint probieren
                    
                    if response.status_code in [200, 201]:
                        print(f"API-Upload erfolgreich: {endpoint}")
                        try:
                            return response.json()
                        except:
                            return {"success": True, "endpoint": endpoint}
                            
                except Exception:
                    continue
        
        return None

    def _store_locally(self, machine: str, code: str, description: str) -> dict:
        """Speichert Maschinenfehler lokal"""
        timestamp = datetime.now().isoformat()
        formatted_text = f"Maschine {machine}: Fehler {code} – {description} (Zeit: {timestamp})"
        
        error_data = {
            "timestamp": timestamp,
            "machine": machine,
            "code": code,
            "description": description,
            "formatted_text": formatted_text,
            "anythingllm_import_text": f"[Maschinenfehler OPC UA]\n{formatted_text}\n\nMaschine: {machine}\nFehlercode: {code}\nBeschreibung: {description}\nZeitstempel: {timestamp}\n" + "="*60
        }
        
        try:
            os.makedirs("/app/data", exist_ok=True)
            date_str = datetime.now().strftime('%Y%m%d')
            
            # JSON-Datei für strukturierte Daten
            json_filename = f"/app/data/machine_errors_{date_str}.json"
            if os.path.exists(json_filename):
                with open(json_filename, 'r') as f:
                    errors = json.load(f)
            else:
                errors = []
            
            errors.append(error_data)
            
            with open(json_filename, 'w') as f:
                json.dump(errors, f, indent=2, ensure_ascii=False)
            
            # Text-Datei für AnythingLLM-Import
            import_filename = f"/app/data/anythingllm_import_{date_str}.txt"
            with open(import_filename, 'a', encoding='utf-8') as f:
                f.write(f"\n{error_data['anythingllm_import_text']}\n")
            
            print(f"Maschinenfehler lokal gespeichert: {machine}/{code}")
            print(f"JSON: {json_filename}")
            print(f"Import: {import_filename}")
            
            return {
                "success": True,
                "local_storage": True,
                "json_file": json_filename,
                "import_file": import_filename,
                "anythingllm_text": error_data['anythingllm_import_text']
            }
            
        except Exception as e:
            print(f"Lokale Speicherung fehlgeschlagen: {e}")
            return {"success": False, "error": str(e)}

    def send_machine_error(self, machine: str, code: str, description: str) -> Optional[dict]:
        """Sendet Maschinenfehler - mit HTML-Erkennung und Fallback"""
        timestamp = datetime.now().isoformat()
        message = f"[Maschinenfehler] Maschine {machine}: Fehler {code} – {description} (Zeit: {timestamp})"
        
        print(f"Versuche Maschinenfehler zu senden: {machine}/{code}")
        
        # Zuerst API-Upload versuchen
        api_result = self._try_api_upload(message)
        
        if api_result:
            print("API-Upload erfolgreich")
            return api_result
        
        print("API-Upload fehlgeschlagen - verwende lokale Speicherung")
        
        # Fallback: Lokale Speicherung
        local_result = self._store_locally(machine, code, description)
        
        if local_result.get("success"):
            print("Maschinenfehler wurde lokal gespeichert")
            print("Für AnythingLLM-Import:")
            print(f"  1. Datei ansehen: cat {local_result.get('import_file')}")
            print(f"  2. Text kopieren und in AnythingLLM Web-Interface einfügen")
            print(f"  3. AnythingLLM-URL: {self.base_url}")
        
        return local_result

    def get_stored_errors(self, date: str = None) -> list:
        """Gibt gespeicherte Fehler zurück"""
        if date is None:
            date = datetime.now().strftime('%Y%m%d')
        
        filename = f"/app/data/machine_errors_{date}.json"
        
        try:
            if os.path.exists(filename):
                with open(filename, 'r') as f:
                    return json.load(f)
            return []
        except Exception as e:
            print(f"Fehler beim Laden der Daten: {e}")
            return []

    def get_import_text(self, date: str = None) -> str:
        """Gibt den Import-Text für AnythingLLM zurück"""
        if date is None:
            date = datetime.now().strftime('%Y%m%d')
        
        filename = f"/app/data/anythingllm_import_{date}.txt"
        
        try:
            if os.path.exists(filename):
                with open(filename, 'r', encoding='utf-8') as f:
                    return f.read()
            return "Keine Daten für dieses Datum gefunden."
        except Exception as e:
            return f"Fehler beim Laden: {e}"

def send_to_anythingllm(machine, code, description):
    """Kompatibilitätsfunktion für Ihren ursprünglichen Code"""
    client = AnythingLLMClient()
    return client.send_machine_error(machine, code, description)

# Zusätzliche Hilfsfunktionen
def show_stored_errors():
    """Zeigt alle gespeicherten Fehler des heutigen Tages"""
    client = AnythingLLMClient()
    errors = client.get_stored_errors()
    print(f"Gespeicherte Fehler heute ({len(errors)} Stück):")
    for error in errors:
        print(f"  {error['timestamp']}: {error['machine']}/{error['code']} - {error['description']}")

def get_anythingllm_import_text():
    """Gibt den Import-Text für AnythingLLM zurück"""
    client = AnythingLLMClient()
    return client.get_import_text()
