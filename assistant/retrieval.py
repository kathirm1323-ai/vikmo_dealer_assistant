"""
Retrieval module — ChromaDB vector store with semantic search.

Strategy:
- Each product row in the catalogue becomes one document.
- Fields are concatenated into a rich text chunk for embedding.
- Uses sentence-transformers/all-MiniLM-L6-v2 for embeddings (free, fast).
- ChromaDB stores vectors persistently in ./chroma_db/.
- Retrieval uses cosine similarity, returning top-k=5 results.
"""

import os
import pandas as pd
import chromadb
from chromadb.utils import embedding_functions

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "catalogue.csv")
CHROMA_DIR = os.path.join(os.path.dirname(__file__), "..", "chroma_db")
COLLECTION_NAME = "product_catalogue"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_document(row: pd.Series) -> str:
    """Convert a catalogue row into a rich text document for embedding."""
    fitment = str(row['vehicle_fitment']).strip()

    if fitment.lower() == "universal":
        compat_text = (
            "Universal fitment — fits all bikes, motorcycles, and scooters. "
            "Compatible with any make and model"
        )
    else:
        compat_text = f"Compatible with {fitment}"

    return (
        f"{row['name']} | Category: {row['category']} | Brand: {row['brand']} | "
        f"{compat_text} | "
        f"Price: ₹{row['price_inr']} | Stock: {row['stock']} units | "
        f"SKU: {row['sku']} | {row['description']}"
    )


def load_catalogue() -> pd.DataFrame:
    """Load the product catalogue CSV into a DataFrame."""
    df = pd.read_csv(DATA_PATH)
    return df


# ---------------------------------------------------------------------------
# Vector Store
# ---------------------------------------------------------------------------

class ProductVectorStore:
    """Manages the ChromaDB collection for product catalogue search."""

    def __init__(self):
        self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBEDDING_MODEL
        )
        self.client = chromadb.PersistentClient(path=CHROMA_DIR)
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=self.embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )
        self.catalogue_df = load_catalogue()

    def index_catalogue(self, force_reindex: bool = False) -> int:
        """
        Index the product catalogue into ChromaDB.

        Args:
            force_reindex: If True, delete existing collection and re-index.

        Returns:
            Number of documents indexed.
        """
        # Check if already indexed and matches catalogue size
        if self.collection.count() == len(self.catalogue_df) and not force_reindex:
            return self.collection.count()

        # If count does not match, force a re-indexing to ensure correct data
        force_reindex = True

        # Clear if re-indexing
        if force_reindex and self.collection.count() > 0:
            self.client.delete_collection(COLLECTION_NAME)
            self.collection = self.client.get_or_create_collection(
                name=COLLECTION_NAME,
                embedding_function=self.embedding_fn,
                metadata={"hnsw:space": "cosine"},
            )

        documents = []
        ids = []
        metadatas = []

        for _, row in self.catalogue_df.iterrows():
            doc_text = _row_to_document(row)
            documents.append(doc_text)
            ids.append(row["sku"])
            metadatas.append({
                "sku": row["sku"],
                "product_name": row["name"],
                "category": row["category"],
                "brand": row["brand"],
                "vehicle_fitment": row["vehicle_fitment"],
                "price": float(row["price_inr"]),
                "stock": int(row["stock"]),
            })

        # ChromaDB supports batch add
        self.collection.add(
            documents=documents,
            ids=ids,
            metadatas=metadatas,
        )

        return len(documents)

    def search(self, query: str, k: int = 5) -> list[dict]:
        """
        Semantic search for products matching the query.

        Args:
            query: Natural language search query.
            k: Number of results to return.

        Returns:
            List of dicts with product info and relevance score.
        """
        results = self.collection.query(
            query_texts=[query],
            n_results=min(k, self.collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        products = []
        if results and results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                products.append({
                    "sku": doc_id,
                    "document": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i],
                })

        # Re-ranking: Boost exact SKU matches to the top
        query_upper = query.upper()
        boosted = []
        standard = []
        for p in products:
            if p["sku"] in query_upper:
                boosted.append(p)
            else:
                standard.append(p)
        
        products = boosted + standard

        return products

    def get_product_by_sku(self, sku: str) -> dict | None:
        """Look up a single product by SKU from the DataFrame."""
        row = self.catalogue_df[self.catalogue_df["sku"] == sku.upper()]
        if row.empty:
            return None
        d = row.iloc[0].to_dict()
        if "name" in d and "product_name" not in d:
            d["product_name"] = d["name"]
        if "price_inr" in d and "price" not in d:
            d["price"] = d["price_inr"]
        return d

    def find_by_vehicle(self, make: str, model: str, year: int) -> list[dict]:
        """Filter catalogue by vehicle compatibility using fuzzy matching."""
        df = self.catalogue_df
        make_lower = make.strip().lower()
        model_lower = model.strip().lower()

        # Since year doesn't exist in the new dataset, we ignore the year parameter.
        # Match if vehicle_fitment is "Universal" or contains both make and model.
        fitment_series = df["vehicle_fitment"].str.lower()

        make_match = (fitment_series == "universal") | fitment_series.str.contains(make_lower, na=False)
        model_match = (fitment_series == "universal") | fitment_series.str.contains(model_lower, na=False)

        mask = make_match & model_match
        results = df[mask].copy()

        # If no results, try partial matching on model words
        if results.empty:
            model_words = model_lower.split()
            for word in model_words:
                if len(word) >= 3:
                    partial_mask = (
                        ((fitment_series == "universal") | fitment_series.str.contains(make_lower, na=False))
                        & fitment_series.str.contains(word, na=False)
                    )
                    partial_results = df[partial_mask].copy()
                    if not partial_results.empty:
                        results = partial_results
                        break

        # Map new column names to keys expected by tools/agent/frontend
        if not results.empty:
            results["product_name"] = results["name"]
            results["price"] = results["price_inr"]
        return results.to_dict("records")


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_store: ProductVectorStore | None = None


def get_store() -> ProductVectorStore:
    """Get or create the singleton vector store instance."""
    global _store
    if _store is None:
        _store = ProductVectorStore()
        _store.index_catalogue()
    return _store


def search_products(query: str, k: int = 5) -> list[dict]:
    """Convenience function for product search."""
    store = get_store()
    return store.search(query, k)
