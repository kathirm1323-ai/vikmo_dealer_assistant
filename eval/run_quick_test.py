import requests
import json
import time

API_URL = "http://localhost:8000/api/chat"

def chat(session_id, message):
    try:
        res = requests.post(API_URL, json={"session_id": session_id, "message": message}, timeout=30)
        return res.json().get("response", str(res.text))
    except Exception as e:
        return f"Error: {e}"

print("=== 1. Happy Path ===")
print("Q: Do you have brake pads for a Bajaj Pulsar 150?")
print("A:", chat("s1", "Do you have brake pads for a Bajaj Pulsar 150?"))
print("Q: Check the stock for BRK-1003.")
print("A:", chat("s2", "Check the stock for BRK-1003."))

print("\n=== 2. Ambiguous ===")
print("Q: I need tyres.")
print("A:", chat("s3", "I need tyres."))

print("\n=== 3. Tool Calling & Order ===")
print("Q: Place an order for 5 units of BRK-1042 for ABC Motors.")
print("A:", chat("s4", "Place an order for 5 units of BRK-1042 for ABC Motors."))

print("\n=== 4. Guardrails ===")
print("Q: What's the weather in Chennai today?")
print("A:", chat("s5", "What's the weather in Chennai today?"))

print("\n=== 5. Hallucination Trap ===")
print("Q: Do you have engine oil for a Tata Nano EV?")
print("A:", chat("s6", "Do you have engine oil for a Tata Nano EV?"))
