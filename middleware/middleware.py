from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import requests
import asyncio

app = FastAPI()

clients = []

OLLAMA_URL = "http://ollama:11434/v1/chat/completions"
MODEL = "llama3.2:latest"   # Passe das Modell an, das du in Ollama installiert hast


@app.post("/chat/send")
async def chat_send(message: dict):
    user_msg = message.get("message", "")

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": user_msg}]
    }
    r = requests.post(OLLAMA_URL, json=payload)

    if r.status_code != 200:
        return {"error": "Ollama request failed", "detail": r.text}

    bot_reply = r.json()["choices"][0]["message"]["content"]

    await broadcast({"user": user_msg, "bot": bot_reply})
    return {"reply": bot_reply}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    clients.append(ws)
    try:
        while True:
            data = await ws.receive_text()
            await broadcast({"user": data})
    except WebSocketDisconnect:
        clients.remove(ws)


async def broadcast(message: dict):
    disconnected = []
    for ws in clients:
        try:
            await ws.send_json(message)
        except:
            disconnected.append(ws)
    for ws in disconnected:
        clients.remove(ws)
