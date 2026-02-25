# -*- coding: utf-8 -*-
"""
WritingBot Web API Server (Enterprise)
=======================================

Flask-based REST API for the WritingBot RAG system.
Uses enterprise-grade data and session management.
"""

import os
import uuid
import shutil
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Add src to path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from src.parsing.pdf_parser import PDFParser
from src.processing.semantic_chunker import SemanticChunker
from src.knowledge.kb_manager import KnowledgeBaseManager
from src.knowledge.vector_store import VectorStore
from src.session.manager import SessionManager
from src.rag.engine import RAGEngine

app = Flask(__name__)
CORS(app)

# Configuration
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

# Initialize Enterprise Managers
kb_manager = KnowledgeBaseManager(DATA_DIR / "knowledge_bases")
session_manager = SessionManager(DATA_DIR / "sessions")

# Global instances (lazy loaded)
_parser = None


def get_parser():
    global _parser
    if _parser is None:
        _parser = PDFParser()
    return _parser


def get_vector_store(kb_id: str) -> VectorStore:
    """Get VectorStore for a specific KB."""
    kb = kb_manager.get_kb(kb_id)
    if not kb:
        raise ValueError(f"KB not found: {kb_id}")
    
    vector_path = kb_manager.get_vector_store_path(kb_id)
    
    # Use provider/model from KB metadata (with sensible defaults)
    embedding_provider = kb.get("embedding_provider", "sentence-transformers")
    embedding_model = kb.get("embedding_model", "sentence-transformers/all-mpnet-base-v2")

    return VectorStore(
        persist_dir=str(vector_path),
        collection_name=kb["collection_name"],
        embedding_model=embedding_model,
        embedding_provider=embedding_provider
    )


# ============== Knowledge Base API ==============

@app.route('/api/kbs', methods=['GET'])
def list_kbs():
    return jsonify({"success": True, "data": kb_manager.list_kbs()})


@app.route('/api/kbs', methods=['POST'])
def create_kb():
    data = request.json
    if not data or 'name' not in data:
        return jsonify({"success": False, "error": "Name is required"}), 400
    
    name = data['name']
    description = data.get('description', "")
    
    # Provider selection
    embedding_provider = data.get('embedding_provider', "sentence-transformers")
    embedding_model = data.get('embedding_model')

    # Defaults based on provider
    if not embedding_model:
        if embedding_provider == "ollama":
            embedding_model = "nomic-embed-text:latest"
        elif embedding_provider == "openai":
            embedding_model = "text-embedding-3-small"
        else:
            embedding_model = "sentence-transformers/all-mpnet-base-v2"
    
    kb = kb_manager.create_kb(name, embedding_model, embedding_provider, description)
    return jsonify({"success": True, "data": kb})


@app.route('/api/kbs/<kb_id>', methods=['DELETE'])
def delete_kb(kb_id):
    if kb_manager.delete_kb(kb_id):
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "KB not found"}), 404


@app.route('/api/kbs/<kb_id>', methods=['GET'])
def get_kb_details(kb_id):
    kb = kb_manager.get_kb(kb_id)
    if not kb:
        return jsonify({"success": False, "error": "KB not found"}), 404
    
    try:
        vs = get_vector_store(kb_id)
        stats = vs.get_stats()
        return jsonify({"success": True, "data": {"metadata": kb, "stats": stats}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/kbs/<kb_id>/ingest', methods=['POST'])
def ingest_file(kb_id):
    kb = kb_manager.get_kb(kb_id)
    if not kb:
        return jsonify({"success": False, "error": "KB not found"}), 404

    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file provided"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected"}), 400
    
    if not file.filename.lower().endswith('.pdf'):
        return jsonify({"success": False, "error": "Only PDF files are supported"}), 400
    
    chunk_size = int(request.form.get('chunk_size', 1000))
    chunk_overlap = int(request.form.get('chunk_overlap', 200))

    try:
        file_id = str(uuid.uuid4())
        filename = file.filename
        
        # Save to KB's raw directory
        raw_dir = kb_manager.get_raw_path(kb_id)
        raw_dir.mkdir(parents=True, exist_ok=True)
        filepath = raw_dir / f"{file_id}_{filename}"
        file.save(str(filepath))
        
        # Parse PDF
        parser = get_parser()
        content_list = parser.parse(str(filepath))
        
        # Chunk content
        chunker = SemanticChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        chunks = chunker.chunk_content_list(content_list)
        
        # Add metadata to chunks
        for chunk in chunks:
            if chunk.metadata:
                chunk.metadata['source'] = filename
                chunk.metadata['file_id'] = file_id
        
        # Index in vector store
        vs = get_vector_store(kb_id)
        chunk_dicts = [c.to_dict() for c in chunks]
        vs.add_chunks(chunk_dicts)
        
        # Record file info
        file_info = {
            "id": file_id,
            "name": filename,
            "path": str(filepath),
            "size": filepath.stat().st_size,
            "uploaded_at": datetime.now().isoformat(),
            "blocks": len(content_list),
            "chunks": len(chunks)
        }
        kb_manager.add_file(kb_id, file_info)
        
        return jsonify({"success": True, "data": file_info})
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/kbs/<kb_id>/files/<file_id>', methods=['DELETE'])
def delete_file(kb_id, file_id):
    kb = kb_manager.get_kb(kb_id)
    if not kb:
        return jsonify({"success": False, "error": "KB not found"}), 404
    kb_manager.remove_file(kb_id, file_id)
    return jsonify({"success": True})


# ============== Conversation API ==============

@app.route('/api/conversations', methods=['GET'])
def list_conversations():
    return jsonify({"success": True, "data": session_manager.list_sessions()})


@app.route('/api/conversations', methods=['POST'])
def create_conversation():
    data = request.json or {}
    session_id = str(uuid.uuid4())
    
    session = session_manager.get_or_create(
        session_id,
        title=data.get("title", "New Chat"),
        kb_id=data.get("kb_id")
    )
    session_manager.save(session)
    
    return jsonify({"success": True, "data": session.to_dict()})


@app.route('/api/conversations/<conv_id>', methods=['GET'])
def get_conversation(conv_id):
    session = session_manager.get(conv_id)
    if not session:
        return jsonify({"success": False, "error": "Conversation not found"}), 404
    return jsonify({"success": True, "data": session.to_dict()})


@app.route('/api/conversations/<conv_id>', methods=['DELETE'])
def delete_conversation(conv_id):
    session_manager.delete(conv_id)
    return jsonify({"success": True})


# ============== Chat API ==============

@app.route('/api/chat', methods=['POST'])
def chat():
    """Non-streaming chat endpoint (kept for compatibility)."""
    try:
        data = request.json
        if not data or 'message' not in data:
            return jsonify({"success": False, "error": "No message provided"}), 400
        
        message = data['message']
        conv_id = data.get('conversation_id')
        kb_id = data.get('kb_id')
        
        # Get or create session
        if conv_id:
            session = session_manager.get(conv_id)
            if not session:
                session = session_manager.get_or_create(
                    conv_id,
                    title=message[:30] + "..." if len(message) > 30 else message,
                    kb_id=kb_id
                )
            if not kb_id:
                kb_id = session.metadata.get('kb_id')
        else:
            conv_id = str(uuid.uuid4())
            session = session_manager.get_or_create(
                conv_id,
                title=message[:30] + "..." if len(message) > 30 else message,
                kb_id=kb_id
            )
        
        if not kb_id:
            return jsonify({"success": False, "error": "No Knowledge Base selected"}), 400
        
        # Add user message
        user_msg = session.add_message("user", message)
        
        # Query RAG engine
        vs = get_vector_store(kb_id)
        engine = RAGEngine(vector_store=vs)
        result = engine.query(message)
        
        # Add assistant message
        assistant_msg = session.add_message(
            "assistant",
            result["answer"],
            sources=result.get("sources", [])
        )
        
        # Save session
        session_manager.save(session)
        
        return jsonify({
            "success": True,
            "data": {
                "conversation_id": conv_id,
                "message": assistant_msg
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/chat/stream', methods=['POST'])
def chat_stream():
    """
    Streaming chat endpoint using Server-Sent Events (SSE).
    
    Response format:
    - Text chunks: data: {"type": "chunk", "content": "..."}
    - Sources: data: {"type": "sources", "data": [...]}
    - Done: data: {"type": "done", "conversation_id": "..."}
    - Error: data: {"type": "error", "error": "..."}
    """
    from flask import Response, stream_with_context
    import json
    
    data = request.json
    if not data or 'message' not in data:
        return jsonify({"success": False, "error": "No message provided"}), 400
    
    message = data['message']
    conv_id = data.get('conversation_id')
    kb_id = data.get('kb_id')
    
    def generate():
        nonlocal conv_id
        
        # Send padding to exhaust browser/proxy buffers (usually 1-2KB)
        yield f": {' ' * 2048}\n\n"
        
        try:
            # ... (session creation logic)
            if conv_id:
                session = session_manager.get(conv_id)
                if not session:
                    session = session_manager.get_or_create(
                        conv_id,
                        title=message[:30] + "..." if len(message) > 30 else message,
                        kb_id=kb_id
                    )
                session_kb_id = kb_id or session.metadata.get('kb_id')
            else:
                conv_id = str(uuid.uuid4())
                session = session_manager.get_or_create(
                    conv_id,
                    title=message[:30] + "..." if len(message) > 30 else message,
                    kb_id=kb_id
                )
                session_kb_id = kb_id or session.metadata.get('kb_id') # Fix: ensure session_kb_id fallback
            
            if not session_kb_id:
                yield f"data: {json.dumps({'type': 'error', 'error': 'No Knowledge Base selected'})}\n\n"
                return
            
            # Add user message
            session.add_message("user", message)
            
            # Create RAG engine
            vs = get_vector_store(session_kb_id)
            engine = RAGEngine(vector_store=vs)
            
            # Stream response
            full_response = ""
            sources = []
            
            # Use streaming query
            print(f"Starting stream for message: {message[:20]}...")
            gen = engine.query_stream(message)
            
            for chunk in gen:
                full_response += chunk
                # Send chunk to client
                print(f"Yielding chunk: {chunk[:10]}...", flush=True) # Debug print
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
            
            # Get sources from generator return (if available)
            # Note: In Python, generator return value is in StopIteration.value
            # But we've already consumed it, so we need to get sources differently
            # We'll retrieve them again (fast, already cached)
            context, sources = engine._retrieve_context(message)
            
            # Send sources
            yield f"data: {json.dumps({'type': 'sources', 'data': sources})}\n\n"
            
            # Save assistant message
            session.add_message("assistant", full_response, sources=sources)
            session_manager.save(session)
            
            # Send done signal
            yield f"data: {json.dumps({'type': 'done', 'conversation_id': conv_id})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
    
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',  # Disable nginx buffering
            'Access-Control-Allow-Origin': '*',  # CORS for SSE
            'Access-Control-Allow-Headers': 'Content-Type',
        }
    )


if __name__ == '__main__':
    print("\n" + "="*60)
    print("  WritingBot API Server (Enterprise)")
    print("  Backend: http://localhost:5000")
    print("  Frontend: http://localhost:3000 (run: npm run dev)")
    print("="*60 + "\n")
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)

