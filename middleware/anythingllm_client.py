import requests
import os
import json
import time
import logging
import sys
from typing import Optional, Dict, Any
from datetime import datetime
from icon_standards import get_icon, get_http_icon, get_status_icon, format_http_response, format_retry_message, ICONS

CLIENT_VERSION = "anyllm_client_v20250909_2212_007"

def log_and_print(level: str, message: str, *args):
    """Hilfsfunktion: Print-Ausgabe mit Icon-Standards"""
    formatted_message = message % args if args else message
    
    # Icon basierend auf Log-Level
    level_icon = get_icon("log_level", level, ICONS["log_level"]["info"])
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {level_icon} {formatted_message}")

class AnythingLLMClient:
    """Client für AnythingLLM API-Integration mit Retry-Mechanismus und Fallback"""
    
    def __init__(self):
        self.base_url = os.getenv("ANYTHINGLLM_URL", "http://localhost:3001")
        self.api_key = os.getenv("ANYTHINGLLM_API_KEY", "DEIN_API_KEY")
        self.workspace_slug = os.getenv("ANYTHINGLLM_WORKSPACE", "wago-edge-copilot")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self.timeout = int(os.getenv("ANYTHINGLLM_TIMEOUT", "30"))
        self.max_retries = int(os.getenv("ANYTHINGLLM_RETRIES", "3"))
        
        log_and_print("INFO", f"{ICONS['system']['start']} AnythingLLM Client initialisiert: %s", self.base_url)
        log_and_print("INFO", f"{ICONS['data']['config']} Client Version: %s", CLIENT_VERSION)
        log_and_print("INFO", f"{ICONS['workspace']['active']} Konfigurierter Workspace: %s", self.workspace_slug)
        log_and_print("INFO", f"{ICONS['time']['timer']} Timeout: %ds, Retries: %d", self.timeout, self.max_retries)

    def get_workspaces(self) -> Dict[str, Any]:
        """Ruft alle verfügbaren Workspaces ab"""
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/workspaces", 
                headers=self.headers, 
                timeout=10
            )
            
            status_icon = get_http_icon(response.status_code)
            
            if response.status_code == 200:
                log_and_print("INFO", f"{status_icon} Workspaces erfolgreich abgerufen (HTTP %d)", response.status_code)
                return response.json()
            else:
                log_and_print("WARNING", f"{status_icon} Workspaces abrufen fehlgeschlagen: HTTP %d", response.status_code)
                return {}
        except Exception as e:
            error_icon = get_status_icon("error")
            log_and_print("ERROR", f"{error_icon} Fehler beim Abrufen der Workspaces: %s", e)
            return {}

    def log_available_workspaces(self):
        """Loggt alle verfügbaren Workspaces beim Startup"""
        log_and_print("INFO", f"{ICONS['system']['loading']} Lade verfügbare AnythingLLM Workspaces...")
        
        workspaces_data = self.get_workspaces()
        
        if not workspaces_data:
            offline_icon = get_status_icon("offline")
            log_and_print("WARNING", f"{offline_icon} Keine Workspaces gefunden oder API nicht erreichbar")
            return
        
        workspaces = workspaces_data.get("workspaces", [])
        
        if not workspaces:
            warning_icon = get_status_icon("warning")
            log_and_print("WARNING", f"{warning_icon} Workspace-Liste ist leer")
            return
        
        log_and_print("INFO", f"{ICONS['data']['folder']} Verfügbare Workspaces (%d gefunden):", len(workspaces))
        print("-" * 60)
        
        for workspace in workspaces:
            workspace_id = workspace.get("id")
            workspace_name = workspace.get("name", "Unbekannt")
            workspace_slug = workspace.get("slug", "unbekannt")
            created_at = workspace.get("createdAt", "")
            
            # Datum formatieren
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    created_str = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    created_str = created_at[:10]
            else:
                created_str = "Unbekannt"
            
            # Workspace-Status
            is_active = workspace_slug == self.workspace_slug
            status_icon = get_status_icon("online" if is_active else "standby")
            
            log_and_print("INFO", f"{status_icon} ID: %s | Name: %s", workspace_id, workspace_name)
            log_and_print("INFO", f"    {ICONS['time']['calendar']} Slug: %s | Erstellt: %s", workspace_slug, created_str)
            
            # API-URL für diesen Workspace
            api_url = f"{self.base_url}/api/v1/workspace/{workspace_slug}/chat"
            log_and_print("INFO", f"    {ICONS['network']['api']} API: %s", api_url)
            print("")
        
        print("-" * 60)
        active_icon = get_status_icon("online")
        log_and_print("INFO", f"{active_icon} Aktiver Workspace: %s", self.workspace_slug)
        
        # Prüfen ob der konfigurierte Workspace existiert
        configured_exists = any(ws.get("slug") == self.workspace_slug for ws in workspaces)
        if not configured_exists:
            error_icon = get_status_icon("error")
            log_and_print("ERROR", f"{error_icon} WARNUNG: Konfigurierter Workspace '%s' nicht gefunden!", self.workspace_slug)
            available_slugs = [ws.get("slug") for ws in workspaces]
            info_icon = get_status_icon("standby")
            log_and_print("ERROR", f"{info_icon} Verfügbare Slugs: %s", available_slugs)

    def test_connection(self) -> bool:
        """Testet die Verbindung zu AnythingLLM"""
        try:
            log_and_print("INFO", f"{ICONS['network']['ping']} Teste AnythingLLM Verbindung...")
            response = requests.get(f"{self.base_url}/api/ping", timeout=5)
            
            status_icon = get_http_icon(response.status_code)
            
            if response.status_code == 200:
                result = response.json()
                if result.get("online"):
                    log_and_print("SUCCESS", f"{status_icon} AnythingLLM-Ping erfolgreich (HTTP %d)", response.status_code)
                    
                    # Nach erfolgreichem Ping Workspaces laden
                    self.log_available_workspaces()
                    return True
            
            log_and_print("WARNING", f"{status_icon} AnythingLLM-Ping fehlgeschlagen: Status %d", response.status_code)
            return False
            
        except Exception as e:
            error_icon = get_status_icon("error")
            log_and_print("ERROR", f"{error_icon} AnythingLLM-Verbindungstest fehlgeschlagen: %s", e)
            return False

    def send_machine_error(self, machine: str, code: str, description: str) -> Optional[Dict[str, Any]]:
        """Sendet Maschinenfehler an AnythingLLM mit Retry-Mechanismus"""
        timestamp = datetime.now().isoformat()
        message = f"[Maschinenfehler] Maschine {machine}: Fehler {code} – {description} (Zeit: {timestamp})"
        
        # Chat-URL und Payload vorbereiten
        chat_url = f"{self.base_url}/api/v1/workspace/{self.workspace_slug}/chat"
        payload = {"message": message}
        
        log_and_print("INFO", f"{ICONS['machine']['factory']} Starte API-Übertragung: %s/%s", machine, code)
        
        # Retry-Mechanismus
        for attempt in range(self.max_retries):
            try:
                retry_msg = format_retry_message(attempt + 1, self.max_retries, "Sende an AnythingLLM")
                log_and_print("INFO", retry_msg)
                
                response = requests.post(
                    chat_url,
                    headers=self.headers,
                    json=payload,
                    timeout=self.timeout
                )
                
                http_response = format_http_response(response.status_code, "AnythingLLM Response")
                log_and_print("INFO", http_response)
                
                if response.status_code == 200:
                    try:
                        result = response.json()
                        success_icon = get_icon("process", "success")
                        log_and_print("SUCCESS", f"{success_icon} AnythingLLM API erfolgreich (Versuch %d): %s/%s", 
                                      attempt + 1, machine, code)
                        
                        # ERFOLG: Sofort return - keine weiteren Versuche!
                        return {
                            "success": True,
                            "api_response": True,
                            "anythingllm_response": result.get('textResponse', ''),
                            "sources": result.get('sources', []),
                            "response_id": result.get('id'),
                            "attempt": attempt + 1,
                            "method": "api"
                        }
                        
                    except json.JSONDecodeError as e:
                        error_icon = get_icon("process", "error")
                        log_and_print("ERROR", f"{error_icon} Invalid JSON response (Versuch %d): %s", attempt + 1, e)
                        log_and_print("DEBUG", "Raw response: %s", response.text[:500])
                        
                else:
                    status_icon = get_http_icon(response.status_code)
                    log_and_print("WARNING", f"{status_icon} HTTP Error %d (Versuch %d): %s", 
                                 response.status_code, attempt + 1, response.text[:200])
                             
            except requests.exceptions.Timeout:
                timeout_icon = get_status_icon("timeout")
                log_and_print("WARNING", f"{timeout_icon} Timeout bei Versuch %d/%d (nach %ds)", 
                             attempt + 1, self.max_retries, self.timeout)
                             
            except requests.exceptions.ConnectionError as e:
                connection_icon = get_status_icon("error")
                log_and_print("ERROR", f"{connection_icon} Verbindungsfehler bei Versuch %d: %s", attempt + 1, e)
                
            except Exception as e:
                error_icon = get_icon("process", "error")
                log_and_print("ERROR", f"{error_icon} API-Fehler bei Versuch %d: %s", attempt + 1, e)
                # Bei unerwarteten Fehlern: Retry-Schleife verlassen
                break
            
            # Wartezeit zwischen Versuchen (nur wenn nicht letzter Versuch)
            if attempt < self.max_retries - 1:
                # Längere Wartezeit bei Timeout
                wait_time = 5 if 'Timeout' in str(sys.exc_info()[1]) else 2
                waiting_icon = get_icon("process", "pending")
                #log_and_print("INFO", f"{waiting_icon} Warte %ds vor nächstem Versuch...", wait_time)
                time.sleep(wait_time)
        
        # Nur hier ankommen wenn ALLE Versuche fehlgeschlagen sind
        failed_icons = f"{ICONS['retry']['failed']} {ICONS['retry']['failed']} {ICONS['retry']['failed']}"
        log_and_print("ERROR", f"{failed_icons} Alle %d API-Versuche fehlgeschlagen - verwende lokale Speicherung", 
                      self.max_retries)
        return self._store_locally(machine, code, description)

    def _store_locally(self, machine: str, code: str, description: str) -> Dict[str, Any]:
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
            
            # JSON-Datei für strukturierte Daten
            json_filename = f"/app/data/machine_errors_{date_str}.json"
            if os.path.exists(json_filename):
                with open(json_filename, 'r', encoding='utf-8') as f:
                    errors = json.load(f)
            else:
                errors = []
            
            errors.append(error_data)
            
            with open(json_filename, 'w', encoding='utf-8') as f:
                json.dump(errors, f, indent=2, ensure_ascii=False)
            
            # Import-Text für AnythingLLM
            import_filename = f"/app/data/anythingllm_import_{date_str}.txt"
            with open(import_filename, 'a', encoding='utf-8') as f:
                f.write(f"\n{error_data['anythingllm_import_text']}\n")
            
            success_icon = get_icon("process", "success")
            log_and_print("SUCCESS", f"{success_icon} Maschinenfehler lokal gespeichert: %s/%s", machine, code)
            log_and_print("DEBUG", f"{ICONS['data']['json']} JSON: %s, {ICONS['data']['file']} Import: %s", 
                         json_filename, import_filename)
            
            return {
                "success": True,
                "local_storage": True,
                "api_response": False,
                "json_file": json_filename,
                "import_file": import_filename,
                "method": "local_storage"
            }
            
        except Exception as e:
            error_icon = get_icon("process", "error")
            log_and_print("ERROR", f"{error_icon} Lokale Speicherung fehlgeschlagen: %s", e)
            return {
                "success": False,
                "error": str(e),
                "method": "failed"
            }

    def send_chat_message(self, message: str, conversation_id: str = None) -> Optional[Dict[str, Any]]:
        """Sendet eine Chat-Nachricht an AnythingLLM"""
        chat_url = f"{self.base_url}/api/v1/workspace/{self.workspace_slug}/chat"
        
        payload = {"message": message}
        if conversation_id:
            payload["conversationId"] = conversation_id
        
        try:
            log_and_print("DEBUG", f"{ICONS['network']['api']} Sende Chat-Nachricht: %s", message[:100])
            response = requests.post(
                chat_url, 
                headers=self.headers, 
                json=payload, 
                timeout=self.timeout
            )
            
            status_icon = get_http_icon(response.status_code)
            
            if response.status_code == 200:
                result = response.json()
                log_and_print("SUCCESS", f"{status_icon} Chat-Nachricht erfolgreich gesendet")
                return result
            else:
                log_and_print("WARNING", f"{status_icon} Chat-Nachricht fehlgeschlagen: HTTP %d", response.status_code)
                return None
                
        except Exception as e:
            error_icon = get_icon("process", "error")
            log_and_print("ERROR", f"{error_icon} Chat-Fehler: %s", e)
            return None

    def get_stored_errors(self, date: str = None) -> list:
        """Gibt gespeicherte Fehler zurück"""
        if date is None:
            date = datetime.now().strftime('%Y%m%d')
        
        filename = f"/app/data/machine_errors_{date}.json"
        
        try:
            if os.path.exists(filename):
                with open(filename, 'r', encoding='utf-8') as f:
                    errors = json.load(f)
                    success_icon = get_icon("process", "success")
                    log_and_print("SUCCESS", f"{success_icon} %d Fehler aus lokaler Datei geladen", len(errors))
                    return errors
            
            standby_icon = get_status_icon("standby")
            log_and_print("INFO", f"{standby_icon} Keine lokalen Fehler für %s gefunden", date)
            return []
        except Exception as e:
            error_icon = get_icon("process", "error")
            log_and_print("ERROR", f"{error_icon} Fehler beim Laden der Daten: %s", e)
            return []

    def health_check(self) -> Dict[str, Any]:
        """Vollständiger Gesundheitscheck"""
        log_and_print("INFO", f"{ICONS['system']['health']} Führe Gesundheitscheck durch...")
        
        health = {
            "anythingllm_ping": False,
            "workspace_exists": False,
            "api_key_valid": False,
            "local_storage": False,
            "config": {
                "base_url": self.base_url,
                "workspace_slug": self.workspace_slug,
                "timeout": self.timeout,
                "retries": self.max_retries
            }
        }
        
        # Ping-Test
        try:
            response = requests.get(f"{self.base_url}/api/ping", timeout=5)
            health["anythingllm_ping"] = response.status_code == 200 and response.json().get("online", False)
            
            ping_icon = get_status_icon("online" if health["anythingllm_ping"] else "offline")
            status_text = "Erfolgreich" if health["anythingllm_ping"] else "Fehlgeschlagen"
            log_and_print("INFO", f"{ping_icon} Ping-Test: %s", status_text)
        except:
            error_icon = get_status_icon("error")
            log_and_print("WARNING", f"{error_icon} Ping-Test fehlgeschlagen")
        
        # Workspace-Test
        if health["anythingllm_ping"]:
            workspaces_data = self.get_workspaces()
            workspaces = workspaces_data.get("workspaces", [])
            health["workspace_exists"] = any(ws.get("slug") == self.workspace_slug for ws in workspaces)
            health["api_key_valid"] = len(workspaces) > 0
            
            ws_icon = get_status_icon("online" if health["workspace_exists"] else "error")
            api_icon = get_status_icon("online" if health["api_key_valid"] else "error")
            
            ws_text = "Gefunden" if health["workspace_exists"] else "Nicht gefunden"
            api_text = "Gültig" if health["api_key_valid"] else "Ungültig"
            
            log_and_print("INFO", f"{ws_icon} Workspace-Check: %s", ws_text)
            log_and_print("INFO", f"{api_icon} API-Key-Check: %s", api_text)
        
        # Lokale Speicherung testen
        try:
            os.makedirs("/app/data", exist_ok=True)
            test_file = "/app/data/health_check.tmp"
            with open(test_file, 'w') as f:
                f.write("test")
            os.remove(test_file)
            health["local_storage"] = True
            
            storage_icon = get_icon("process", "success")
            log_and_print("SUCCESS", f"{storage_icon} Lokale Speicherung: Funktionsfähig")
        except:
            storage_icon = get_icon("process", "error")
            log_and_print("ERROR", f"{storage_icon} Lokale Speicherung: Fehlgeschlagen")
        
        return health


def send_to_anythingllm(machine: str, code: str, description: str) -> Optional[Dict[str, Any]]:
    """Kompatibilitätsfunktion für einfache Nutzung"""
    client = AnythingLLMClient()
    return client.send_machine_error(machine, code, description)


if __name__ == "__main__":
    # Test-Skript
    print(f"{ICONS['system']['start']} AnythingLLM Client Test")
    print("=" * 40)
    
    client = AnythingLLMClient()
    
    # Verbindungstest
    if client.test_connection():
        success_icon = get_icon("process", "success")
        log_and_print("SUCCESS", f"{success_icon} Verbindung erfolgreich")
        
        # Health Check
        health = client.health_check()
        print(f"Health Check: {health}")
        
        # Test-Nachricht senden
        result = client.send_machine_error("TestMaschine", "E999", "Client-Test")
        print(f"Test-Ergebnis: {result}")
        
    else:
        error_icon = get_icon("process", "error")
        log_and_print("ERROR", f"{error_icon} Verbindung fehlgeschlagen")
