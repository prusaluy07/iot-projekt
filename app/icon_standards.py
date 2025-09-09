"""
Icon Standards für IoT-AnythingLLM Bridge
=========================================

Zentrale Datei für alle Icons und Status-Symbole.
Verwenden Sie get_icon() für dynamische Icons basierend auf Status.

Verwendung:
    from icon_standards import get_icon, ICONS
    
    # Dynamisches Icon basierend auf HTTP-Status
    icon = get_icon("http_status", 200)
    
    # Festes Icon
    icon = ICONS["process"]["start"]
"""

from typing import Any, Dict, Optional

# =============================================================================
# ICON-KATEGORIEN
# =============================================================================

ICONS = {
    # System & Prozesse
    "system": {
        "start": "▶️",
        "stop": "⏹️", 
        "pause": "⏸️",
        "restart": "🔄",
        "loading": "🔄",
        "refresh": "🔃",
        "sync": "🔃",
        "power": "⚡",
        "settings": "⚙️",
        "config": "🔧",
        "health": "🏥",
        "heartbeat": "💓"
    },
    
    # Status-Ampel (Hauptkategorien)
    "status": {
        "online": "🟢",      # Grün - Online/Aktiv/Erfolg
        "standby": "🔵",     # Blau - Standby/Info/Verarbeitung
        "warning": "🟡",     # Gelb - Warnung/Teilweise
        "offline": "🔴",     # Rot - Offline/Fehler/Kritisch
        "unknown": "⚪",     # Weiß - Unbekannt/Neutral
        "disabled": "⚫"     # Schwarz - Deaktiviert
    },
    
    # Log-Level
    "log_level": {
        "info": "ℹ️",
        "success": "✅", 
        "warning": "⚠️",
        "error": "❌",
        "debug": "🔍",
        "trace": "📝"
    },
    
    # Netzwerk & Kommunikation
    "network": {
        "connected": "🟢",
        "connecting": "🔵", 
        "disconnected": "🔴",
        "timeout": "🟡",
        "signal": "📡",
        "wifi": "📶",
        "ethernet": "🌐",
        "api": "🔗",
        "endpoint": "🎯",
        "ping": "📊"
    },
    
    # HTTP Status Codes
    "http": {
        "1xx": "🔵",  # Informational
        "2xx": "🟢",  # Success
        "3xx": "🔵",  # Redirection
        "4xx": "🔴",  # Client Error
        "5xx": "🟡",  # Server Error
        "unknown": "⚪"
    },
    
    # Maschinen & Hardware
    "machine": {
        "running": "🟢",
        "maintenance": "🟡",
        "error": "🔴",
        "stopped": "⚪",
        "factory": "🏭",
        "robot": "🤖",
        "sensor": "📡",
        "motor": "⚙️",
        "pump": "🔄",
        "valve": "🚿",
        "pressure": "💨",
        "temperature": "🌡️"
    },
    
    # Dateien & Daten
    "data": {
        "file": "📄",
        "folder": "📁", 
        "database": "🗄️",
        "json": "📋",
        "csv": "📊",
        "log": "📝",
        "config": "⚙️",
        "backup": "💾",
        "import": "📥",
        "export": "📤",
        "save": "💾",
        "load": "📂"
    },
    
    # Prozess-Zustände
    "process": {
        "start": "▶️",
        "running": "🔵",
        "success": "🟢", 
        "warning": "🟡",
        "error": "🔴",
        "failed": "❌",
        "completed": "✅",
        "pending": "⏳",
        "queued": "📋",
        "retry": "🔄"
    },
    
    # Retry & Versuche
    "retry": {
        "first": "🔵",     # Erster Versuch
        "normal": "🟡",    # 2-3 Versuche
        "many": "🔴",      # 4+ Versuche
        "timeout": "⏰",   # Timeout
        "failed": "❌"     # Komplett fehlgeschlagen
    },
    
    # Sicherheit & Authentifizierung
    "security": {
        "locked": "🔒",
        "unlocked": "🔓",
        "key": "🔑",
        "shield": "🛡️",
        "user": "👤",
        "group": "👥",
        "admin": "👑",
        "auth_success": "✅",
        "auth_failed": "❌"
    },
    
    # Zeit & Planung
    "time": {
        "clock": "🕐",
        "timer": "⏱️",
        "stopwatch": "⏱️",
        "calendar": "📅",
        "schedule": "📆",
        "deadline": "⏰",
        "waiting": "⏳",
        "duration": "⌛"
    },
    
    # Monitoring & Metriken
    "monitoring": {
        "dashboard": "📊",
        "chart": "📈",
        "trend_up": "📈",
        "trend_down": "📉",
        "metrics": "📊",
        "alert": "🚨",
        "notification": "🔔",
        "bell": "🔔"
    },
    
    # Workspace & Container
    "workspace": {
        "active": "✅",
        "inactive": "⚪",
        "container": "📦",
        "docker": "🐳",
        "kubernetes": "☸️",
        "cloud": "☁️"
    }
}

# =============================================================================
# DYNAMISCHE ICON-FUNKTIONEN
# =============================================================================

def get_icon(category: str, value: Any, fallback: str = "⚪") -> str:
    """
    Gibt dynamisches Icon basierend auf Kategorie und Wert zurück.
    
    Args:
        category: Icon-Kategorie (z.B. "http_status", "connection", "process")
        value: Wert zur Bewertung (z.B. HTTP-Code, Status-String)
        fallback: Standard-Icon falls kein Match
        
    Returns:
        Unicode-Icon als String
        
    Examples:
        >>> get_icon("http_status", 200)
        '🟢'
        >>> get_icon("connection", "online")
        '🟢'
        >>> get_icon("retry_attempt", 1)
        '🔵'
    """
    
    if category == "http_status":
        if isinstance(value, int):
            if 100 <= value < 200:
                return ICONS["http"]["1xx"]
            elif 200 <= value < 300:
                return ICONS["http"]["2xx"]
            elif 300 <= value < 400:
                return ICONS["http"]["3xx"]
            elif 400 <= value < 500:
                return ICONS["http"]["4xx"]
            elif 500 <= value < 600:
                return ICONS["http"]["5xx"]
    
    elif category == "connection":
        value_lower = str(value).lower()
        if value_lower in ["connected", "online", "bereit", "erfolgreich", "success"]:
            return ICONS["status"]["online"]
        elif value_lower in ["connecting", "standby", "wartet", "verarbeitung", "processing"]:
            return ICONS["status"]["standby"]
        elif value_lower in ["warning", "teilweise", "timeout", "partial"]:
            return ICONS["status"]["warning"]
        elif value_lower in ["disconnected", "offline", "fehler", "fehlgeschlagen", "error", "failed"]:
            return ICONS["status"]["offline"]
        elif value_lower in ["disabled", "deaktiviert", "stopped"]:
            return ICONS["status"]["disabled"]
    
    elif category == "process":
        value_lower = str(value).lower()
        if value_lower in ["success", "completed", "erfolgreich", "fertig"]:
            return ICONS["process"]["success"]
        elif value_lower in ["running", "processing", "läuft", "active"]:
            return ICONS["process"]["running"]
        elif value_lower in ["warning", "partial", "warnung", "teilweise"]:
            return ICONS["process"]["warning"]
        elif value_lower in ["error", "failed", "fehler", "fehlgeschlagen"]:
            return ICONS["process"]["error"]
        elif value_lower in ["pending", "waiting", "wartend", "queued"]:
            return ICONS["process"]["pending"]
    
    elif category == "retry_attempt":
        if isinstance(value, int):
            if value == 1:
                return ICONS["retry"]["first"]
            elif 2 <= value <= 3:
                return ICONS["retry"]["normal"]
            elif value >= 4:
                return ICONS["retry"]["many"]
    
    elif category == "machine_status":
        value_lower = str(value).lower()
        if value_lower in ["running", "active", "läuft", "aktiv"]:
            return ICONS["machine"]["running"]
        elif value_lower in ["maintenance", "wartung", "service"]:
            return ICONS["machine"]["maintenance"]
        elif value_lower in ["error", "fehler", "alarm", "critical"]:
            return ICONS["machine"]["error"]
        elif value_lower in ["stopped", "inactive", "gestoppt", "inaktiv"]:
            return ICONS["machine"]["stopped"]
    
    elif category == "log_level":
        value_lower = str(value).lower()
        if value_lower in ["info", "information"]:
            return ICONS["log_level"]["info"]
        elif value_lower in ["success", "ok", "erfolgreich"]:
            return ICONS["log_level"]["success"]
        elif value_lower in ["warning", "warn", "warnung"]:
            return ICONS["log_level"]["warning"]
        elif value_lower in ["error", "err", "fehler"]:
            return ICONS["log_level"]["error"]
        elif value_lower in ["debug", "trace"]:
            return ICONS["log_level"]["debug"]
    
    return fallback


def get_log_icon(level: str) -> str:
    """Shortcut für Log-Level Icons"""
    return get_icon("log_level", level, ICONS["log_level"]["info"])


def get_status_icon(status: str) -> str:
    """Shortcut für Status Icons"""
    return get_icon("connection", status, ICONS["status"]["unknown"])


def get_http_icon(status_code: int) -> str:
    """Shortcut für HTTP Status Icons"""
    return get_icon("http_status", status_code, ICONS["http"]["unknown"])


def get_machine_icon(status: str) -> str:
    """Shortcut für Maschinen-Status Icons"""
    return get_icon("machine_status", status, ICONS["machine"]["stopped"])


# =============================================================================
# ICON-KOMBINATIONEN FÜR HÄUFIGE ANWENDUNGSFÄLLE
# =============================================================================

def format_status_message(status: str, message: str, use_icon: bool = True) -> str:
    """
    Formatiert Status-Nachricht mit Icon.
    
    Args:
        status: Status-String für Icon-Auswahl
        message: Nachricht
        use_icon: Ob Icon verwendet werden soll
        
    Returns:
        Formatierte Nachricht mit Icon
    """
    if use_icon:
        icon = get_status_icon(status)
        return f"{icon} {message}"
    return message


def format_http_response(status_code: int, message: str) -> str:
    """Formatiert HTTP-Response mit Status-Icon"""
    icon = get_http_icon(status_code)
    return f"{icon} HTTP {status_code}: {message}"


def format_retry_message(attempt: int, max_attempts: int, message: str) -> str:
    """Formatiert Retry-Nachricht mit Versuchs-Icon"""
    icon = get_icon("retry_attempt", attempt)
    return f"{icon} Versuch {attempt}/{max_attempts}: {message}"


# =============================================================================
# VERWENDUNGSBEISPIELE & DOKUMENTATION
# =============================================================================

def _usage_examples():
    """Beispiele für die Verwendung der Icon-Standards"""
    
    # HTTP Status Icons
    print("HTTP Status Icons:")
    for code in [200, 301, 404, 500]:
        icon = get_http_icon(code)
        print(f"  {icon} HTTP {code}")
    
    # Connection Status
    print("\nConnection Status:")
    for status in ["online", "connecting", "timeout", "offline"]:
        icon = get_status_icon(status)
        print(f"  {icon} {status}")
    
    # Retry Attempts
    print("\nRetry Attempts:")
    for attempt in [1, 2, 4, 8]:
        icon = get_icon("retry_attempt", attempt)
        print(f"  {icon} Attempt {attempt}")
    
    # Machine Status
    print("\nMachine Status:")
    for status in ["running", "maintenance", "error", "stopped"]:
        icon = get_machine_icon(status)
        print(f"  {icon} Machine {status}")


if __name__ == "__main__":
    print("IoT Bridge Icon Standards")
    print("=" * 40)
    _usage_examples()
