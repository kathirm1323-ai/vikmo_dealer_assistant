import requests
import json
import time

API_URL = "http://localhost:8000/api/chat"

def chat(session_id, message):
    res = requests.post(API_URL, json={"session_id": session_id, "message": message})
    return res.json().get("response", str(res.text))

print("=== 1. RAG Retrieval Tests ===")
print("Q: Find products for KTM Duke 390")
print("A:", chat("rag-2", "Find products for KTM Duke 390"))
print("\nQ: Recommend tyres under ₹3000")
print("A:", chat("rag-3", "Recommend tyres under ₹3000"))
print("\nQ: Cheapest chain lube available")
print("A:", chat("rag-4", "Cheapest chain lube available"))
print("\nQ: Bosch products in stock")
print("A:", chat("rag-5", "Bosch products in stock"))

print("\n=== 2. Tool Calling Tests ===")
print("Q: Is SKU BRK-1042 in stock?")
print("A:", chat("tool-1", "Is SKU BRK-1042 in stock?"))
print("\nQ: Check stock for ENG-2001")
print("A:", chat("tool-2", "Check stock for ENG-2001"))
print("\nQ: Find parts for Honda Activa 6G")
print("A:", chat("tool-3", "Find parts for Honda Activa 6G"))
print("\nQ: Place order for 10 units of BRK-1042 for ABC Motors")
print("A:", chat("tool-4", "Place order for 10 units of BRK-1042 for ABC Motors"))

print("\n=== 3. Multi-turn Conversation Tests ===")
sid = "multi-1"
print("Q: I need brake pads.")
print("A:", chat(sid, "I need brake pads."))
print("Q: Bajaj Pulsar 150.")
print("A:", chat(sid, "Bajaj Pulsar 150."))

sid2 = "multi-2"
print("\nQ: I need tyres.")
print("A:", chat(sid2, "I need tyres."))
print("Q: KTM Duke 390.")
print("A:", chat(sid2, "KTM Duke 390."))

print("\n=== 4. Ambiguous Query Tests ===")
print("Q: I need oil")
print("A:", chat("ambig-1", "I need oil"))
print("\nQ: Show batteries")
print("A:", chat("ambig-2", "Show batteries"))
print("\nQ: Recommend spare parts")
print("A:", chat("ambig-3", "Recommend spare parts"))

print("\n=== 5. Order Creation Tests ===")
print("Q: Order 10 BRK-1042")
print("A:", chat("order-1", "Order 10 BRK-1042"))
print("\nQ: Order 5 tyres and 3 air filters")
print("A:", chat("order-2", "Order 5 tyres and 3 air filters"))
print("\nQ: Place order for XYZ Motors")
print("A:", chat("order-3", "Place order for XYZ Motors"))

print("\n=== 6. Guardrail Tests ===")
print("Q: What's the weather today?")
print("A:", chat("gr-1", "What's the weather today?"))
print("\nQ: Who is the Prime Minister of India?")
print("A:", chat("gr-2", "Who is the Prime Minister of India?"))
print("\nQ: Write a Python program")
print("A:", chat("gr-3", "Write a Python program"))
print("\nQ: Tell me a joke")
print("A:", chat("gr-4", "Tell me a joke"))

print("\n=== 7. Hallucination Tests ===")
print("Q: Ask for a product that doesn't exist (Flying car engine)")
print("A:", chat("hal-1", "Do you have an engine for a flying car?"))
print("\nQ: Ask for unavailable stock (1000 units of BRK-1002)")
print("A:", chat("hal-2", "Order 1000 units of BRK-1002 for ABC Motors"))
