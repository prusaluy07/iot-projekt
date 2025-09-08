import requests
import os
import json
import time
import logging
from typing import Optional
from datetime import datetime

logger = logging.getLogger("iot-bridge.anythingllm")

class AnythingLLMClient:
    def __init__(self):
        self.base_url = os.getenv("ANYTHINGLLM_URL", "http://localhost:3001")
        self.api_key = os.getenv("ANYTHINGLLM_API_KEY", "DEIN_API_KEY")
        self.workspace_slug = "wago-edge-copilot"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self.timeout = int(os.getenv("ANYTHINGLLM_TIMEOUT", "30"))
        self.max_retries = int(os.getenv("ANYTHINGLLM_RETRIES", "3"))
        
        logger.info("AnythingLLM Client initialisiert: %s", self.base_url)
        logger.info("Workspace: %s", self.workspace_slug)

    def test_connection(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/api/ping", timeout=5)
            if response.status_code == 200:
                result = response.json()
                if result.get("online"):
                    logger.info("AnythingLLM-Verbindung erfolgreich getestet")
                    return True
            return False
        except Exception as e:
            logger.exception("AnythingLLM-Verbindungstest fehlgeschlagen: %s", e)
            return False

    def send_machine_error(self, machine: str, code: str, description: str) -> Optional[dict]:
        timestamp = datetime.now().isoformat()
        message = f"[Maschinenfehler] Maschine {machine}: Fehler {code} – {description} (Zeit: {timestamp})"
        
        # Chat-URL und Payload vorbereiten
        chat_url = f"{self.base_url}/api/v1/workspace/{self.workspace_slug}/chat"
        payload = {"message": message}
        
        # Retry-Mechanismus
        for attempt in range(self.max_retries):
            try:
                logger.debug("Sende an AnythingLLM (Versuch %d/%d): %s", 
                           attempt + 1, self.max_retries, chat_url)
                
                response = requests.post(
                    chat_url,
                    headers=self.headers,
                    json=payload,
                    timeout=self.timeout
                )
                
                logger.debug("AnythingLLM Response Status: %d", response.status_code)
                
                if response.status_code == 200:
                    try:
                        result = response.json()
                        logger.info("AnythingLLM API erfolgreich: %s/%s", machine, code)
                        
                        return {
                            "success": True,
                            "api_response": True,
                            "anythingllm_response": result.get('textResponse', ''),
                            "sources": result.get('sources', []),
                            "response_id": result.get('id'),
                            "attempt": attempt + 1
                        }
                    except json.JSONDecodeError as e:
                        logger.error("Invalid JSON response (Versuch %d): %s", attempt + 1, e)
                        if attempt < self.max_retries - 1:
                            time.sleep(2)
                            continue
                else:
                    logger.warning("HTTP Error %d (Versuch %d): %s", 
                                 response.status_code, attempt + 1, response.text[:200])
                    if attempt < self.max_retries - 1:
                        time.sleep(2)
                        continue
                        
            except requests.exceptions.Timeout:
                logger.warning("Timeout bei Versuch %d/%d (nach %ds)", 
                             attempt + 1, self.max_retries, self.timeout)
                if attempt < self.max_retries - 1:
                    time.sleep(5)  # Längere Pause bei Timeout
                else:
                    logger.error("Alle Timeout-Versuche fehlgeschlagen")
                    
            except requests.exceptions.ConnectionError as e:
                logger.error("Verbindungsfehler bei Versuch %d: %s", attempt + 1, e)
                if attempt < self.max_retries - 1:
                    time.sleep(3)
                else:
                    break
                    
            except Exception as e:
                logger.exception("API-Fehler bei Versuch %d: %s", attempt + 1, e)
                break
        
        # Fallback zu lokaler Speicherung
        logger.info("API-Upload fehlgeschlagen - verwende lokale Speicherung")
        return self._store_locally(machine, code, description)

    def _store_locally(self, machine: str, code: str, description: str) -> dict:
        """Speichert Maschinenfehler lokal als Fallback"""
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
            
            # JSON-Datei
            json_filename = f"/app/data/machine_errors_{date_str}.json"
            if os.path.exists(json_filename):
                with open(json_filename, 'r') as f:
                    errors = json.load(f)
            else:
                errors = []
            
            errors.append(error_data)
            
            with open(json_filename, 'w') as f:
                json.dump(errors, f, indent=2, ensure_ascii=False)
            
            # Import-Text
            import_filename = f"/app/data/anythingllm_import_{date_str}.txt"
            with open(import_filename, 'a', encoding='utf-8') as f:
                f.write(f"\n{error_data['anythingllm_import_text']}\n")
            
            logger.info("Maschinenfehler lokal gespeichert: %s/%s", machine, code)
            
            return {
                "success": True,
                "local_storage": True,
                "api_response": False,
                "json_file": json_filename,
                "import_file": import_filename
            }
            
        except Exception as e:
            logger.exception("Lokale Speicherung fehlgeschlagen: %s", e)
            return {"success": False, "error": str(e)}

    def send_chat_message(self, message: str, conversation_id: str = None) -> Optional[dict]:
        """Sendet eine Chat-Nachricht an AnythingLLM"""
        chat_url = f"{self.base_url}/api/v1/workspace/{self.workspace_slug}/chat"
        
        payload = {"message": message}
        if conversation_id:
            payload["conversationId"] = conversation_id
        
        try:
            response = requests.post(chat_url, headers=self.headers, json=payload, timeout=self.timeout)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.exception("Chat-Fehler: %s", e)
            return None

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
            logger.exception("Fehler beim Laden der Daten: %s", e)
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
    """Kompatibilitätsfunktion"""
    client = AnythingLLMClient()
    return client.send_machine_error(machine, code, description)
