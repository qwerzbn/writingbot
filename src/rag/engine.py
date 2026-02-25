# -*- coding: utf-8 -*-
"""
RAG Engine - Retrieval-Augmented Generation (Streaming + Chinese)
==================================================================

Core RAG logic with:
- Hybrid retrieval strategy (always retrieve, always call LLM)
- Streaming response support for typewriter effect
- Chinese language output
"""

import os
from typing import List, Dict, Any, Optional, Generator

from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class RAGEngine:
    """
    RAG Engine with hybrid retrieval and streaming support.
    """
    
    SYSTEM_PROMPT = """你是一个智能知识库助手 WritingBot。

你的任务是根据提供的上下文回答用户的问题。

### 核心原则
1. **优先使用上下文**：如果提供的【参考上下文】包含回答问题所需的信息，请主要依据上下文回答，并引用来源。
2. **灵活应对**：如果【参考上下文】为空或与问题完全无关（例如用户只是打招呼、问你是谁、或询问通用知识），请**忽略上下文**，利用你自己的知识进行自然、流畅的对话。
3. **诚实原则**：如果知识库中没有相关信息，且问题是关于特定私有知识的，请明确告知用户知识库中未找到相关内容。

### 回复格式
- 使用中文回答。
- 引用来源格式：[来源: 文件名, 第X页]。
- 保持语气专业、乐于助人。

---
【参考上下文】开始：
{context}
【参考上下文】结束
---

请根据以上原则回答用户的问题。"""
    
    def __init__(self, 
                 vector_store,
                 llm_api_key: Optional[str] = None,
                 llm_base_url: Optional[str] = None,
                 llm_model: Optional[str] = None):
        """Initialize RAG engine."""
        self.vector_store = vector_store
        
        # LLM configuration
        self.llm_api_key = llm_api_key or os.getenv("LLM_API_KEY")
        self.llm_base_url = llm_base_url or os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
        self.llm_model = llm_model or os.getenv("LLM_MODEL", "gpt-4o-mini")
        
        # Check if LLM is available
        self.llm_enabled = bool(self.llm_api_key and self.llm_api_key != "your_api_key_here")
        
        # Conversation history
        self.history: List[Dict[str, str]] = []
        
        # LLM client (lazy initialization)
        self._llm_client = None
        
        if self.llm_enabled:
            print(f"LLM enabled: {self.llm_model}")
        else:
            print("LLM not configured. Will return retrieved context only.")
    
    def _get_llm_client(self):
        """Get or create OpenAI-compatible client."""
        if self._llm_client is None and self.llm_enabled:
            try:
                from openai import OpenAI
                self._llm_client = OpenAI(
                    api_key=self.llm_api_key,
                    base_url=self.llm_base_url
                )
            except ImportError:
                print("OpenAI package not installed. LLM generation disabled.")
                self.llm_enabled = False
        return self._llm_client
    
    def _retrieve_context(self, question: str, top_k: int = 5) -> tuple[str, List[Dict]]:
        """Retrieve context from vector store."""
        results = self.vector_store.search(question, top_k=top_k)
        
        context_parts = []
        sources = []
        
        for i, result in enumerate(results, 1):
            source = result["metadata"].get("source", "Unknown")
            page = result["metadata"].get("page", "?")
            content = result["content"]
            
            context_parts.append(f"[{i}] {content}\n[来源: {source}, 第{page}页]")
            sources.append({
                "source": source,
                "page": page,
                "score": result.get("score", 0)
            })
        
        context = "\n\n".join(context_parts) if context_parts else "(知识库中暂无文档)"
        return context, sources
    
    def query(self, 
              question: str, 
              top_k: int = 5,
              use_history: bool = True) -> Dict[str, Any]:
        """Non-streaming query (kept for compatibility)."""
        context, sources = self._retrieve_context(question, top_k)
        
        if self.llm_enabled:
            answer = self._generate_answer(question, context, use_history)
        else:
            answer = f"**检索到的上下文:**\n\n{context}"
        
        if use_history:
            self.history.append({"role": "user", "content": question})
            self.history.append({"role": "assistant", "content": answer})
        
        return {
            "answer": answer,
            "sources": sources,
            "context": context
        }
    
    def query_stream(self, 
                     question: str, 
                     top_k: int = 5,
                     use_history: bool = True) -> Generator[str, None, Dict[str, Any]]:
        """
        Streaming query - yields text chunks as they arrive.
        
        Usage:
            gen = engine.query_stream("问题")
            for chunk in gen:
                print(chunk, end='', flush=True)
            # Final result is returned when generator exhausts
        
        Yields:
            str: Text chunks as they stream from the LLM
            
        Returns:
            Dict with 'sources' after streaming completes
        """
        # 1. Retrieve context (blocking, fast)
        context, sources = self._retrieve_context(question, top_k)
        
        # 2. Stream LLM response
        if not self.llm_enabled:
            # No LLM, yield context directly
            fallback = f"**检索到的上下文:**\n\n{context}"
            yield fallback
            return {"sources": sources, "context": context}
        
        client = self._get_llm_client()
        if not client:
            yield "LLM 客户端初始化失败"
            return {"sources": sources, "context": context}
        
        # Build messages
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT.format(context=context)}
        ]
        
        if use_history and self.history:
            recent_history = self.history[-8:]
            messages.extend(recent_history)
        
        messages.append({"role": "user", "content": question})
        
        # Stream from OpenAI
        full_response = ""
        try:
            stream = client.chat.completions.create(
                model=self.llm_model,
                messages=messages,
                temperature=0.7,
                max_tokens=2000,
                stream=True  # Enable streaming
            )
            
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    text = chunk.choices[0].delta.content
                    full_response += text
                    yield text
                    
        except Exception as e:
            error_msg = f"\n\n[错误: {e}]"
            yield error_msg
            full_response += error_msg
        
        # Update history with full response
        if use_history:
            self.history.append({"role": "user", "content": question})
            self.history.append({"role": "assistant", "content": full_response})
        
        return {"sources": sources, "context": context}
    
    def _generate_answer(self, question: str, context: str, use_history: bool) -> str:
        """Generate answer (non-streaming, for compatibility)."""
        client = self._get_llm_client()
        if not client:
            return f"**检索到的上下文:**\n\n{context}"
        
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT.format(context=context)}
        ]
        
        if use_history and self.history:
            recent_history = self.history[-8:]
            messages.extend(recent_history)
        
        messages.append({"role": "user", "content": question})
        
        try:
            response = client.chat.completions.create(
                model=self.llm_model,
                messages=messages,
                temperature=0.7,
                max_tokens=2000
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"生成回答时出错: {e}"
    
    def clear_history(self):
        """Clear conversation history."""
        self.history = []
    
    def get_history(self) -> List[Dict[str, str]]:
        """Get conversation history."""
        return self.history.copy()
