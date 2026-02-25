# -*- coding: utf-8 -*-
"""
WritingBot - Interactive CLI
=============================

Main entry point for the WritingBot RAG system.
Provides an interactive shell for document ingestion and Q&A.

Commands:
    /ingest <path>  - Ingest a PDF file into the knowledge base
    /clear          - Clear conversation history
    /stats          - Show knowledge base statistics
    /help           - Show help message
    /quit           - Exit the application
    <question>      - Ask a question about the ingested documents
"""

import cmd
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.parsing import PDFParser
from src.processing import SemanticChunker
from src.knowledge import VectorStore
from src.rag import RAGEngine


class WritingBotCLI(cmd.Cmd):
    """Interactive CLI for WritingBot."""
    
    intro = """
╔═══════════════════════════════════════════════════════════════╗
║                    WritingBot RAG System                      ║
║                                                               ║
║  Commands:                                                    ║
║    /ingest <path>  - Ingest a PDF file                       ║
║    /clear          - Clear conversation history              ║
║    /stats          - Show KB statistics                      ║
║    /help           - Show this help                          ║
║    /quit           - Exit                                    ║
║                                                               ║
║  Or just type your question to query the knowledge base!     ║
╚═══════════════════════════════════════════════════════════════╝
"""
    prompt = "\n📚 WritingBot > "
    
    def __init__(self):
        super().__init__()
        
        # Setup paths
        self.base_dir = Path(__file__).parent
        self.data_dir = self.base_dir / "data"
        self.kb_dir = self.data_dir / "kb"
        self.vector_dir = self.kb_dir / "vector_store"
        self.content_list_dir = self.kb_dir / "content_list"
        
        # Ensure directories exist
        self.vector_dir.mkdir(parents=True, exist_ok=True)
        self.content_list_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        print("\n⏳ Initializing components...")
        
        self.parser = PDFParser()
        self.chunker = SemanticChunker(chunk_size=1000, chunk_overlap=200)
        self.vector_store = VectorStore(persist_dir=str(self.vector_dir))
        self.rag_engine = RAGEngine(vector_store=self.vector_store)
        
        print("✅ Initialization complete!\n")
    
    def default(self, line: str):
        """Handle questions (any input that's not a command)."""
        if not line.strip():
            return
        
        # Check if it looks like a command
        if line.startswith("/"):
            print(f"❌ Unknown command: {line}")
            print("   Type /help for available commands.")
            return
        
        # It's a question
        self._ask_question(line)
    
    def _ask_question(self, question: str):
        """Process a question and display the answer."""
        print("\n🔍 Searching knowledge base...")
        
        result = self.rag_engine.query(question)
        
        print("\n" + "─" * 60)
        print("📝 Answer:")
        print("─" * 60)
        print(result["answer"])
        
        if result["sources"]:
            print("\n📑 Sources:")
            for src in result["sources"]:
                print(f"   • {src['source']}, Page {src['page']} (score: {src['score']:.2f})")
        print("─" * 60)
    
    def do_ingest(self, arg: str):
        """Ingest a PDF file: /ingest <path>"""
        if not arg.strip():
            print("❌ Usage: /ingest <path_to_pdf>")
            return
        
        file_path = Path(arg.strip())
        if not file_path.exists():
            print(f"❌ File not found: {file_path}")
            return
        
        if not file_path.suffix.lower() == ".pdf":
            print(f"❌ Only PDF files are supported. Got: {file_path.suffix}")
            return
        
        print(f"\n📄 Ingesting: {file_path.name}")
        
        # Step 1: Parse PDF
        print("   Step 1/3: Parsing PDF...")
        try:
            content_list = self.parser.parse(
                str(file_path), 
                output_dir=str(self.content_list_dir)
            )
            print(f"   ✓ Extracted {len(content_list)} text blocks")
        except Exception as e:
            print(f"   ❌ Parsing failed: {e}")
            return
        
        # Step 2: Chunk text
        print("   Step 2/3: Chunking text...")
        chunks = self.chunker.chunk_content_list(content_list)
        print(f"   ✓ Created {len(chunks)} chunks")
        
        # Step 3: Add to vector store
        print("   Step 3/3: Indexing chunks...")
        chunk_dicts = [c.to_dict() for c in chunks]
        self.vector_store.add_chunks(chunk_dicts)
        
        print(f"\n✅ Successfully ingested: {file_path.name}")
        print(f"   Total documents in KB: {self.vector_store.get_stats()['document_count']}")
    
    def do_clear(self, arg: str):
        """Clear conversation history: /clear"""
        self.rag_engine.clear_history()
        print("✅ Conversation history cleared.")
    
    def do_stats(self, arg: str):
        """Show knowledge base statistics: /stats"""
        stats = self.vector_store.get_stats()
        print("\n📊 Knowledge Base Statistics:")
        print(f"   Collection: {stats['collection_name']}")
        print(f"   Documents: {stats['document_count']}")
        print(f"   Embedding Model: {stats['embedding_model']}")
        print(f"   Storage: {stats['persist_dir']}")
    
    def do_help(self, arg: str):
        """Show help message: /help"""
        print(self.intro)
    
    def do_quit(self, arg: str):
        """Exit the application: /quit"""
        print("\n👋 Goodbye!")
        return True
    
    def do_exit(self, arg: str):
        """Exit the application: /exit"""
        return self.do_quit(arg)
    
    # Handle command prefixes
    def precmd(self, line: str) -> str:
        """Pre-process command line."""
        # Strip leading/trailing whitespace
        line = line.strip()
        
        # Handle / prefixed commands
        if line.startswith("/"):
            parts = line[1:].split(maxsplit=1)
            if parts:
                cmd = parts[0].lower()
                arg = parts[1] if len(parts) > 1 else ""
                return f"{cmd} {arg}"
        
        return line
    
    def emptyline(self):
        """Do nothing on empty line."""
        pass


def main():
    """Main entry point."""
    try:
        cli = WritingBotCLI()
        cli.cmdloop()
    except KeyboardInterrupt:
        print("\n\n👋 Interrupted. Goodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()
