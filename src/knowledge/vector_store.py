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
        client = OpenAI(api_key=api_key, base_url=base_url)
        def embed_fn(texts: List[str]) -> List[List[float]]:
            response = client.embeddings.create(model=model, input=texts)
            return [item.embedding for item in response.data]
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
            flat_meta = {
                "source": str(meta.get("source", "")),
                "page": int(meta.get("page", 0)),
                "chunk_idx": int(meta.get("chunk_idx", 0)),
                "start_pos": int(meta.get("start_pos", 0)),
                "end_pos": int(meta.get("end_pos", 0)),
            }
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
