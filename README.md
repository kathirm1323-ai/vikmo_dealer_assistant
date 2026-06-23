# VIKMO — Dealer Assistant 🏍️

> AI-powered automotive parts catalogue assistant for dealers, built with RAG and Tool Calling.

## 🎯 Overview

VIKMO Dealer Assistant helps automotive parts dealers:
- **Search products** from a 600 SKUs parts catalogue using semantic search
- **Check stock** availability by SKU
- **Find compatible parts** for specific vehicles (make, model, year)
- **Place orders** with validated line items and structured JSON responses
- Handle **multi-turn conversations** with context retention
- Reject **out-of-domain queries** with polite guardrails

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| LLM | Llama 3.3 70B (via Groq) |
| Framework | LangChain |
| Vector Store | ChromaDB |
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 |
| Validation | Pydantic v2 |
| Data | Pandas |
| API Server | FastAPI + Uvicorn |
| Frontend | Vanilla HTML/CSS/JS |
| Forecasting | Facebook Prophet |

## 📁 Project Structure

```
Vikmo/
├── README.md                  # This file
├── DESIGN.md                  # Architecture & design decisions
├── requirements.txt           # Python dependencies
├── .env                       # Environment variables
├── app.py                     # FastAPI server
│
├── data/
│   ├── catalogue.csv          # Product catalogue (600 SKUs)
│   └── sales_history.csv      # Sales history (18 months)
│
├── assistant/
│   ├── __init__.py
│   ├── retrieval.py           # ChromaDB vector store + RAG
│   ├── tools.py               # Tool definitions (Pydantic)
│   ├── prompts.py             # System prompts
│   └── agent.py               # LangChain agent orchestration
│
├── eval/
│   ├── eval_set.json          # 26 test cases
│   ├── run_eval.py            # Evaluation runner
│   └── results.md             # Generated eval results
│
├── forecasting/
│   ├── baseline.py            # Last-value & moving average
│   └── forecast.py            # Prophet model
│
└── frontend/
    ├── index.html             # Chat UI
    ├── style.css              # Black/red theme
    └── app.js                 # Frontend logic
```

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.10+
- Free Groq API key from [console.groq.com](https://console.groq.com)

### 2. Install Dependencies

```bash
cd Vikmo
pip install -r requirements.txt
```

### 3. Set Up Environment

```bash
# Create a .env file and add your Groq API key
# GROQ_API_KEY=gsk_your_key_here
```

### 4. Run the Application

```bash
python app.py
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

### 5. Run Evaluation

```bash
python eval/run_eval.py
```

### 6. Run Forecasting

```bash
python forecasting/forecast.py
```

## 💬 Example Conversations

### Product Search
```
User: I need brake pads for Bajaj Pulsar 150
Assistant: Here are the brake pads compatible with your Pulsar 150:
  - Premium Brake Pad Set (SKU001) — ₹850, 120 in stock
  ...
```

### Multi-turn
```
User: I need brake pads
Assistant: For which bike? Please share the make, model, and year.

User: Bajaj Pulsar 150, 2022
Assistant: [retrieves matching products]
```

### Stock Check
```
User: Check stock for SKU001
Assistant: 📦 SKU001 — Premium Brake Pad Set: 120 units in stock ✅
```

### Order Placement
```
User: Order for Sharma Motors: 2x SKU001, 3x SKU029
Assistant: ✅ Order ORD-A1B2C3D4 confirmed! Total: ₹3,650
```

### Guardrails
```
User: What's the weather today?
Assistant: I'm the VIKMO Dealer Assistant and I specialize in
automotive parts. How can I help with your parts needs?
```

## 📊 Evaluation

The evaluation framework includes 26 test cases across 6 categories:

| Category | Test Cases |
|----------|-----------|
| Product Search | 6 |
| Vehicle Fitment | 4 |
| Stock Checking | 3 |
| Order Creation | 3 |
| Ambiguous Requests | 3 |
| Out-of-Scope | 3 |

**Metrics:**
- Retrieval Accuracy
- Tool Calling Accuracy
- Grounded Response Rate

## 📈 Demand Forecasting (Bonus)

- **Dataset:** 18 months of sales history for 30 SKUs
- **Baselines:** Last Value, 3-Month Moving Average
- **Model:** Facebook Prophet (per-SKU)
- **Metrics:** MAE, MAPE
- **No data leakage:** Test set (last 3 months) never seen during training

## 📄 License

Built for the VIKMO AI/ML Intern Assignment.
