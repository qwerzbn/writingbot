# -*- coding: utf-8 -*-
"""
Vector Store - ChromaDB-based Knowledge Storage (Multi-Provider)
=================================================================

Provides persistent vector storage for document chunks using ChromaDB.
Supports multiple embedding providers:
- sentence-transformers (local, default)
- Ollama (local)
- OpenAI (API)
"""

import os
import json
from pathlib import Path
from typing import List, Optional, Dict, Any, Callable

import chromadb
from chromadb.config import Settings
from dotenv import load_dotenv

load_dotenv()


# ==============================================================================
# Embedding Provider Factory
# ==============================================================================

def get_embedding_function(provider: str, model: str, base_url: str = None, api_key: str = None) -> Callable:
    """
    Create an embedding function based on the provider.
    
    Args:
        provider: "sentence-transformers", "ollama", or "openai"
        model: Model name
        base_url: API base URL (for ollama/openai)
        api_key: API key (for openai, use "ollama" for Ollama)
    
    Returns:
        A function that takes a list of texts and returns embeddings
    """
    provider = provider.lower()
    
    if provider == "sentence-transformers":
        from sentence_transformers import SentenceTransformer
        st_model = SentenceTransformer(model)
        def embed_fn(texts: List[str]) -> List[List[float]]:
            embeddings = st_model.encode(texts, show_progress_bar=len(texts) > 10)
            return embeddings.tolist()
        return embed_fn
    
    elif provider == "ollama":
        import requests
        base_url = base_url or "http://localhost:11434"
        # Strip /v1 if present, as we use the native API
        if base_url.endswith("/v1"):
            base_url = base_url[:-3]
            
        # Ollama embeddings endpoint
        def embed_fn(texts: List[str]) -> List[List[float]]:
            embeddings = []
            for text in texts:
                resp = requests.post(
                    f"{base_url}/api/embeddings",
                    json={"model": model, "prompt": text}
                )
                if resp.status_code != 200:
                    raise ValueError(f"Ollama API Error: {resp.text}")
                embeddings.append(resp.json()["embedding"])
            return embeddings
        return embed_fn
    
    elif provider == "openai":
        from openai import OpenAI
        # Fall back to LLM_API_KEY / LLM_BASE_URL if no dedicated embedding key is set
        resolved_api_key = api_key or os.getenv("EMBEDDING_API_KEY") or os.getenv("LLM_API_KEY")
        resolved_base_url = base_url or os.getenv("EMBEDDING_BASE_URL") or os.getenv("LLM_BASE_URL")
        if not resolved_api_key:
            raise ValueError("OpenAI embedding requires an API key. Set OPENAI_API_KEY, LLM_API_KEY, or provide it when creating the knowledge base.")
        client = OpenAI(api_key=resolved_api_key, base_url=resolved_base_url)
        BATCH_SIZE = 6  # DashScope limits batch to 10; use 6 for safety margin
        def embed_fn(texts: List[str]) -> List[List[float]]:
            all_embeddings = []
            for i in range(0, len(texts), BATCH_SIZE):
                batch = texts[i:i + BATCH_SIZE]
                response = client.embeddings.create(model=model, input=batch)
                all_embeddings.extend([item.embedding for item in response.data])
            return all_embeddings
        return embed_fn
    
    else:
        raise ValueError(f"Unknown embedding provider: {provider}")


class VectorStore:
    """
    Vector store using ChromaDB with multi-provider embeddings.
    
    Features:
    - Persistent storage
    - Multiple embedding providers (sentence-transformers, Ollama, OpenAI)
    - Batch embedding and insertion
    - Similarity search with metadata filtering
    """
    
    DEFAULT_COLLECTION = "writingbot_kb"

    @staticmethod
    def _flatten_metadata(meta: Dict[str, Any]) -> Dict[str, Any]:
        flat_meta: Dict[str, Any] = {}
        for key, value in (meta or {}).items():
            if value is None:
                continue
            if isinstance(value, bool):
                flat_meta[str(key)] = value
                continue
            if isinstance(value, int):
                flat_meta[str(key)] = value
                continue
            if isinstance(value, float):
                flat_meta[str(key)] = value
                continue
            if isinstance(value, str):
                flat_meta[str(key)] = value
                continue
            if isinstance(value, (list, tuple, set, dict)):
                flat_meta[str(key)] = json.dumps(value, ensure_ascii=False)
                continue
            flat_meta[str(key)] = str(value)
        return flat_meta
    
    def __init__(self,
                 persist_dir: str,
                 collection_name: Optional[str] = None,
                 embedding_model: Optional[str] = None,
                 embedding_provider: Optional[str] = None,
                 embedding_base_url: Optional[str] = None,
                 embedding_api_key: Optional[str] = None):
        """
        Initialize the vector store.
        
        Args:
            persist_dir: Directory for persistent ChromaDB storage
            collection_name: Name of the collection
            embedding_model: Model name for embeddings
            embedding_provider: "sentence-transformers", "ollama", or "openai"
            embedding_base_url: API base URL (for ollama/openai)
            embedding_api_key: API key (for openai)
        """
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        
        self.collection_name = collection_name or self.DEFAULT_COLLECTION
        
        # Embedding configuration (from env or args)
        self.embedding_provider = embedding_provider or os.getenv("EMBEDDING_PROVIDER", "sentence-transformers")
        self.model_name = embedding_model or os.getenv("EMBEDDING_MODEL", "all-mpnet-base-v2")
        self.embedding_base_url = embedding_base_url or os.getenv("EMBEDDING_BASE_URL")
        self.embedding_api_key = embedding_api_key or os.getenv("EMBEDDING_API_KEY")
        
        # Initialize embedding function
        print(f"Loading embedding model: {self.embedding_provider}/{self.model_name}")
        self._embed = get_embedding_function(
            provider=self.embedding_provider,
            model=self.model_name,
            base_url=self.embedding_base_url,
            api_key=self.embedding_api_key
        )
        
        # Initialize ChromaDB with persistent storage
        self._client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Get or create collection
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        
        print(f"Vector store initialized: {self.collection_name} ({self._collection.count()} documents)")
    
    def add_chunks(self, chunks: List[Dict[str, Any]]) -> int:
        """
        Add chunks to the vector store.
        
        Args:
            chunks: List of chunk dicts with 'content' and 'metadata'
            
        Returns:
            Number of chunks added
        """
        if not chunks:
            return 0
        
        # Extract texts and prepare data
        texts = [c["content"] for c in chunks]
        ids = [f"chunk_{self._collection.count() + i}" for i in range(len(chunks))]
        
        # Prepare metadata (ChromaDB requires flat dict)
        metadatas = []
        for chunk in chunks:
            meta = chunk.get("metadata", {})
            flat_meta = self._flatten_metadata(meta)
            # Keep canonical numeric fields for downstream filters.
            if "page" in meta:
                flat_meta["page"] = int(meta.get("page", 0))
            if "chunk_idx" in meta:
                flat_meta["chunk_idx"] = int(meta.get("chunk_idx", 0))
            if "start_pos" in meta:
                flat_meta["start_pos"] = int(meta.get("start_pos", 0))
            if "end_pos" in meta:
                flat_meta["end_pos"] = int(meta.get("end_pos", 0))
            metadatas.append(flat_meta)
        
        # Generate embeddings
        print(f"Generating embeddings for {len(texts)} chunks...")
        embeddings = self._embed(texts)
        
        # Add to collection
        self._collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas
        )
        
        print(f"Added {len(chunks)} chunks to vector store")
        return len(chunks)
    
    def search(self, 
               query: str, 
               top_k: int = 5,
               filter_metadata: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """
        Search for similar chunks.
        
        Args:
            query: Search query
            top_k: Number of results to return
            filter_metadata: Optional metadata filter
            
        Returns:
            List of results with content, metadata, and score
        """
        # Generate query embedding
        query_embedding = self._embed([query])[0]
        
        # Build query params
        query_params = {
            "query_embeddings": [query_embedding],
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"]
        }
        
        if filter_metadata:
            query_params["where"] = filter_metadata
        
        # Execute search
        results = self._collection.query(**query_params)
        
        # Format results
        formatted = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                formatted.append({
                    "content": doc,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 0.0,
                    "score": 1 - results["distances"][0][i] if results["distances"] else 1.0
                })
        
        return formatted
    
    def get_stats(self) -> Dict[str, Any]:
        """Get collection statistics."""
        return {
            "collection_name": self.collection_name,
            "document_count": self._collection.count(),
            "persist_dir": str(self.persist_dir),
            "embedding_provider": self.embedding_provider,
            "embedding_model": self.model_name
        }
    
    def clear(self) -> bool:
        """Clear all documents from the collection."""
        all_data = self._collection.get()
        if all_data["ids"]:
            self._collection.delete(ids=all_data["ids"])
            print(f"Cleared {len(all_data['ids'])} documents from collection")
        return True

    def delete_by_file_id(self, file_id: str) -> int:
        """Delete all chunks that belong to the given file_id."""
        if not file_id:
            return 0
        rows = self._collection.get(where={"file_id": str(file_id)}, include=["metadatas"])
        ids = rows.get("ids", []) if rows else []
        if not ids:
            return 0
        self._collection.delete(ids=ids)
        return len(ids)

    def list_all_chunks(self) -> list[dict[str, Any]]:
        """Return all chunks with metadata for maintenance tasks."""
        rows = self._collection.get(include=["documents", "metadatas"])
        ids = rows.get("ids", []) if rows else []
        docs = rows.get("documents", []) if rows else []
        metas = rows.get("metadatas", []) if rows else []
        payload: list[dict[str, Any]] = []
        for idx, chunk_id in enumerate(ids):
            payload.append(
                {
                    "id": chunk_id,
                    "content": docs[idx] if idx < len(docs) else "",
                    "metadata": metas[idx] if idx < len(metas) else {},
                }
            )
        return payload

    def repair_missing_file_id(self, file_id: str, source_name: str) -> int:
        """Backfill file_id for historical chunks by matching source filename."""
        if not file_id or not source_name:
            return 0
        rows = self._collection.get(include=["metadatas"])
        ids = rows.get("ids", []) if rows else []
        metas = rows.get("metadatas", []) if rows else []
        patch_ids: list[str] = []
        patch_meta: list[dict[str, Any]] = []
        for idx, chunk_id in enumerate(ids):
            meta = dict(metas[idx] if idx < len(metas) else {})
            source = str(meta.get("source", ""))
            if source != source_name:
                continue
            if str(meta.get("file_id", "")).strip():
                continue
            meta["file_id"] = str(file_id)
            patch_ids.append(chunk_id)
            patch_meta.append(self._flatten_metadata(meta))
        if patch_ids:
            self._collection.update(ids=patch_ids, metadatas=patch_meta)
        return len(patch_ids)
