# DESIGN.md — VIKMO Dealer Assistant

> Technical design document covering retrieval architecture, tool calling, prompt engineering, guardrails, and evaluation methodology.

---

## Table of Contents

1. [Retrieval Architecture](#1-retrieval-architecture)
2. [Embedding Choice](#2-embedding-choice)
3. [ChromaDB Design](#3-chromadb-design)
4. [Tool Calling Strategy](#4-tool-calling-strategy)
5. [Prompt Design](#5-prompt-design)
6. [Guardrails](#6-guardrails)
7. [Evaluation Methodology](#7-evaluation-methodology)
8. [Failure Analysis](#8-failure-analysis)
9. [Demand Forecasting Design](#9-demand-forecasting-design)

---

## 1. Retrieval Architecture

### Overview

The system uses **Retrieval-Augmented Generation (RAG)** to ground LLM responses in actual catalogue data. The complete pipeline:

```
User Query → Embedding → ChromaDB Similarity Search → Top-K Documents → Injected as Context → LLM Generates Response
```

### Chunking Strategy

**Approach: One document per product row.**

Each row in the CSV catalogue becomes a single document. Fields are concatenated into a rich text chunk:

```
"{product_name} | Category: {category} | Brand: {brand} |
Compatible with {make} {model} ({year_start}-{year_end}) |
Price: ₹{price} | Stock: {stock} units | SKU: {sku} | {description}"
```

**Why this approach?**

1. **Atomic granularity** — Each chunk represents exactly one product, making retrieval precise.
2. **No cross-product contamination** — A chunk about brake pads won't include unrelated filter info.
3. **Metadata-rich** — All searchable fields are in the text, so semantic search matches on any attribute.
4. **Simple and deterministic** — No need for complex recursive text splitters; the natural boundary is the product row.

**Alternatives considered:**
- **Category-level chunks**: Would group multiple products, reducing retrieval precision.
- **Field-level chunks**: Too granular — "₹850" alone has no semantic meaning.
- **Overlapping windows**: Unnecessary since products are independent entities.

### Retrieval Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Top-K | 5 | Balances recall vs. context window size |
| Distance Metric | Cosine | Standard for sentence embeddings |
| Re-ranking | Keyword Boost | Exact SKU matches in the query boost corresponding results to the top position |

### Why We Never Send the Entire Catalogue

The system retrieves only top-5 matching products per query (out of 600). This:
- Reduces token usage and latency
- Prevents the LLM from being overwhelmed with irrelevant products
- Forces the response to be focused on what the dealer actually asked about
- Scales to larger catalogues (thousands of products)

---

## 2. Embedding Choice

### Model: `sentence-transformers/all-MiniLM-L6-v2`

| Property | Value |
|----------|-------|
| Dimensions | 384 |
| Model Size | 22M parameters |
| Speed | ~14,000 sentences/sec (CPU) |
| Quality | Competitive on STS benchmarks |
| Cost | Free, no API key needed |

**Why this model?**

1. **Free and local** — No embedding API costs or rate limits.
2. **Fast** — Indexing 600 products takes < 5 seconds.
3. **Good semantic understanding** — Captures meaning of "brake pads for Pulsar" vs just keyword matching.
4. **Small footprint** — 22M params, runs on any machine.

**Alternatives considered:**
- `text-embedding-3-small` (OpenAI): Better quality but requires API key and costs money.
- `all-mpnet-base-v2`: Higher quality but 3x slower; overkill for 600 products.
- `BGE` or `E5` models: Excellent but heavier; not needed at this scale.

---

## 3. ChromaDB Design

### Collection Schema

```python
Collection: "product_catalogue"
├── ID: SKU code (e.g., "SKU001")
├── Document: Concatenated product text
├── Embedding: 384-dim vector (auto-generated)
└── Metadata:
    ├── sku: str
    ├── product_name: str
    ├── category: str
    ├── brand: str
    ├── compatible_make: str
    ├── compatible_model: str
    ├── compatible_year_start: int
    ├── compatible_year_end: int
    ├── price: float
    └── stock: int
```

### Persistence

ChromaDB uses `PersistentClient` with data stored in `./chroma_db/`. This means:
- First run indexes all 600 products (~5 seconds)
- Subsequent runs load from disk (instant)
- Re-indexing available via `force_reindex=True`

### Query Flow

1. User query is embedded using the same model
2. ChromaDB performs approximate nearest neighbor search (HNSW algorithm)
3. Results include documents, metadata, and distance scores
4. Top-K results are formatted and injected into the LLM prompt

---

## 4. Tool Calling Strategy

### Overview

The agent has three tools, each with Pydantic-validated inputs and structured outputs:

### Tool Definitions

| Tool | Input Schema | When Used |
|------|-------------|-----------|
| `check_stock(sku)` | `StockCheckInput(sku: str)` | "Check stock for SKU001" |
| `find_parts_by_vehicle(make, model, year)` | `VehicleFitmentInput(make, model, year)` | "Parts for Pulsar 150 2022" |
| `create_order(dealer_name, line_items)` | `OrderInput(dealer_name, line_items)` | "Order for Sharma Motors..." |

### How Tool Calling Works

1. LangChain's `create_tool_calling_agent` uses Groq's native tool calling support.
2. The LLM decides **autonomously** which tool (if any) to invoke based on the query.
3. Tool descriptions in the `@tool` decorator guide the LLM's decision.
4. Pydantic validates inputs **before** execution — invalid inputs are caught early.
5. Tool outputs are returned as formatted strings that the LLM incorporates into its response.

### Validation Examples

```python
# Stock check — validates SKU format
class StockCheckInput(BaseModel):
    sku: str = Field(description="The SKU code of the product")

# Order — validates each line item
class OrderLineItem(BaseModel):
    sku: str
    quantity: int = Field(ge=1)  # Must be >= 1

class OrderInput(BaseModel):
    dealer_name: str
    line_items: list[OrderLineItem]
```

### Order Processing Logic

1. Validate each line item's SKU exists in catalogue
2. Check sufficient stock for requested quantity
3. Calculate line totals and order total
4. Generate UUID-based order ID
5. Return structured JSON response

---

## 5. Prompt Design

### System Prompt Structure

The system prompt has 6 sections:

1. **Identity** — Defines the assistant as VIKMO Dealer Assistant
2. **Grounding Rules** — ONLY use retrieved catalogue data
3. **Tool Usage** — When to use each tool
4. **Conversation Guidelines** — Ask clarifying questions, maintain context
5. **Guardrails** — Reject out-of-domain queries
6. **Context** — Dynamic section with retrieved products

### Context Injection

Before each LLM call:
1. The user's query is used for RAG retrieval
2. Top-5 matching products are formatted as text
3. This context is injected into the `{context}` placeholder in the system prompt
4. The LLM sees ONLY relevant products, not the entire catalogue

### Temperature Setting

`temperature=0.3` — Low enough for factual accuracy, high enough for natural language flow.

---

## 6. Guardrails

### Domain Filtering

The system prompt explicitly instructs the LLM to:
- Only handle automotive parts queries
- Politely refuse weather, coding, general knowledge questions
- Redirect users back to parts-related topics

### Example Guardrail Response

```
User: What's the capital of France?
Assistant: I'm the VIKMO Dealer Assistant, and I specialize in
automotive parts and accessories. I can help you with product search,
stock checks, vehicle fitment, and order placement.
How can I assist you with your parts needs?
```

### Grounding Enforcement

- The system prompt states: "NEVER make up prices, stock levels, or specifications"
- All product data comes from retrieved documents or tool results
- If no data is found, the assistant says so honestly

### Input Validation

- Pydantic models catch invalid tool inputs (e.g., negative quantities)
- Order creation checks stock availability before confirming
- SKU lookups return clear "not found" messages for invalid SKUs

---

## 7. Evaluation Methodology

### Test Case Design

26 test cases across 6 categories:

| Category | Count | What We Test |
|----------|-------|-------------|
| Product Search | 6 | RAG retrieval accuracy |
| Vehicle Fitment | 4 | Tool selection + parameter extraction |
| Stock Check | 3 | Tool calling with SKU parsing |
| Order Creation | 3 | Complex tool with validation (including failure cases) |
| Ambiguous | 3 | Clarification behavior |
| Out-of-Scope | 3 | Guardrail enforcement |

### Evaluation Criteria

For each test case, we check:

1. **Keyword Match** — Does the response contain expected information?
2. **Grounding** — Is the response based on catalogue data (not hallucinated)?
3. **Tool Selection** — Was the correct tool called (when expected)?

### Metrics

| Metric | Definition |
|--------|-----------|
| **Retrieval Accuracy** | % of tests where expected keywords appear in response |
| **Tool Calling Accuracy** | % of tool-expected tests where the right tool was used |
| **Grounded Response Rate** | % of responses that stay in-domain and use real data |

### Automated Evaluation

```bash
python eval/run_eval.py
```

This:
1. Loads all 26 test cases
2. Runs each through the agent (fresh session per test)
3. Checks keyword presence and grounding
4. Calculates aggregate metrics
5. Generates detailed `eval/results.md`

---

## 8. Failure Analysis

### Evaluation Pass Rate Explanation

The current evaluation pass rate is lower than optimal primarily because the system operates with strict exact-match keyword criteria for grading. This means even semantically correct answers fail if they don't use the exact expected strings. Furthermore, the LLM occasionally struggles to strictly adhere to Pydantic schemas in complex multi-tool scenarios, leading to malformed outputs that fail validation. We prioritize honest reporting of these metrics over artificially inflating scores, and future iterations will focus on prompt refinement and more flexible evaluation heuristics.

### Known Limitations

1. **Ambiguity resolution depends on LLM** — The LLM sometimes guesses the vehicle instead of asking for clarification.

2. **Tool parameter extraction** — Complex natural language like "2 units of the first one and 3 of the oil" may not parse correctly.

3. **Synonym handling** — "disc pads" vs "brake pads" depends on embedding similarity. The embedding model handles common synonyms well but may miss domain-specific jargon.

4. **Stock data is static** — The catalogue is loaded once. In production, you'd need real-time inventory sync.

5. **Single-language** — Currently English only. Indian language support would require multilingual embeddings.

### Mitigation Strategies

- **Clarification prompting** — The system prompt explicitly tells the LLM to ask when unsure.
- **Rich document text** — Including descriptions and category names helps synonym matching.
- **Pydantic validation** — Catches malformed tool inputs before execution.
- **Error handling** — Agent wraps all operations in try/except with user-friendly error messages.

---

## 9. Scaling Considerations

### Scaling to 100,000+ SKUs

The current architecture is optimized for a small catalogue (600 products). If the catalogue were to grow to 100,000 SKUs or more, the system would require the following architectural shifts:

1. **Managed Vector Database**
   - **Current:** Local ChromaDB instance with `PersistentClient`.
   - **Future:** Migrate to a managed vector database like Pinecone, Milvus, or Qdrant. These are designed for sub-millisecond latency at scale, handle distributed queries, and provide high availability.

2. **Metadata Pre-Filtering**
   - **Current:** Semantic search across all 600 documents simultaneously.
   - **Future:** Implement exact-match metadata pre-filtering before semantic search. For instance, if the user asks for "Honda parts", the query would first filter the DB for `metadata["brand"] == "Honda"` or `metadata["compatible_make"] == "Honda"`, drastically reducing the semantic search space and improving precision.

3. **Faster / Dedicated Embedding Models**
   - **Current:** `sentence-transformers/all-MiniLM-L6-v2` running locally.
   - **Future:** While MiniLM is efficient, at extreme scale, utilizing dedicated embedding endpoints (e.g., `text-embedding-3-small` or hosted BGE models) with optimized batching infrastructure will be necessary to handle high concurrency without bottlenecking local compute.

---

## 10. Demand Forecasting Design

### Data Pipeline

```
Sales CSV → Train/Test Split → Baseline Models → Prophet → Compare → Report
```

### Train/Test Split

- **Training:** First 66 weeks of data
- **Test:** Last 12 weeks (held out completely)
- **No leakage:** Test data is never used for training or feature engineering
- **Per-SKU split:** Each product is split independently

### Baseline Models

1. **Last Value** — Forecast = last observed sales value. Simple persistence model.
2. **Moving Average (3-week)** — Forecast = mean of last 3 training values. Smooths noise.

### Prophet Model

- **Per-SKU training** — Individual model for each product
- **Yearly seasonality** — Captures monsoon/festival patterns
- **Conservative changepoints** — `changepoint_prior_scale=0.05` to avoid overfitting
- **Non-negative forecasts** — `max(0, yhat)` to prevent negative predictions

### Metrics

| Metric | Formula | Purpose |
|--------|---------|---------|
| MAE | mean(\|actual - predicted\|) | Average error in units |
| MAPE | mean(\|actual - predicted\| / actual) × 100 | Percentage error (scale-independent) |

### Expected Results

With 18 months of data and clear seasonality, Prophet should:
- Capture the monsoon dip (Jul-Aug lower sales)
- Capture the festival season peak (Oct-Dec higher sales)
- Outperform baselines on MAE, especially for products with strong trends
