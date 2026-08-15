import os
import json
import urllib.request
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()

class Embedder:
    def __init__(self, voyage_key: Optional[str] = None, openai_key: Optional[str] = None):
        self.voyage_key = voyage_key or os.getenv("VOYAGE_API_KEY")
        self.openai_key = openai_key or os.getenv("OPENAI_API_KEY")

        # Determine dimensions
        if self.voyage_key:
            self.model = "voyage-code-2"
            self.dimension = 1024
            print("Embedder initialized with Voyage API (voyage-code-2).")
        elif self.openai_key:
            self.model = "text-embedding-3-small"
            self.dimension = 1536
            print("Embedder initialized with OpenAI API (text-embedding-3-small).")
        else:
            self.model = "mock"
            self.dimension = 384
            print("WARNING: No embedding API keys found. Initializing with mock embedder.")

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embeds a list of texts and returns a list of embeddings (list of floats)."""
        if not texts:
            return []

        if self.model == "voyage-code-2":
            return self._embed_voyage(texts)
        elif self.model == "text-embedding-3-small":
            return self._embed_openai(texts)
        else:
            return self._embed_mock(texts)

    def _embed_voyage(self, texts: List[str]) -> List[List[float]]:
        url = "https://api.voyageai.com/v1/embeddings"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.voyage_key}"
        }
        data = {
            "input": texts,
            "model": self.model
        }
        
        try:
            req = urllib.request.Request(
                url, 
                data=json.dumps(data).encode("utf-8"), 
                headers=headers,
                method="POST"
            )
            with urllib.request.urlopen(req) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                # Voyage response format: {"data": [{"embedding": [...]}, ...]}
                embeddings = [item["embedding"] for item in result["data"]]
                return embeddings
        except Exception as e:
            print(f"Error calling Voyage API: {e}")
            return self._embed_mock(texts)

    def _embed_openai(self, texts: List[str]) -> List[List[float]]:
        url = "https://api.openai.com/v1/embeddings"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.openai_key}"
        }
        data = {
            "input": texts,
            "model": self.model
        }
        
        try:
            req = urllib.request.Request(
                url, 
                data=json.dumps(data).encode("utf-8"), 
                headers=headers,
                method="POST"
            )
            with urllib.request.urlopen(req) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                # OpenAI response format: {"data": [{"embedding": [...]}, ...]}
                embeddings = [item["embedding"] for item in result["data"]]
                return embeddings
        except Exception as e:
            print(f"Error calling OpenAI API: {e}")
            return self._embed_mock(texts)

    def _embed_mock(self, texts: List[str]) -> List[List[float]]:
        """Fallback mock embedder returning deterministic unit vectors based on text hash."""
        import hashlib
        embeddings = []
        for text in texts:
            # Create a simple deterministic vector of size self.dimension
            h = hashlib.sha256(text.encode("utf-8")).digest()
            vector = []
            for i in range(self.dimension):
                # Pseudo-random float from hash bytes
                byte_idx = (i * 7) % len(h)
                val = (h[byte_idx] / 255.0) - 0.5
                vector.append(val)
            
            # Normalize vector
            norm = sum(x*x for x in vector) ** 0.5
            normalized = [x/norm for x in vector] if norm > 0 else [0.0] * self.dimension
            embeddings.append(normalized)
        return embeddings
