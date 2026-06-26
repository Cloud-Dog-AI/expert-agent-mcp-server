# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Vector Store Response Harmonizer

Harmonizes responses from different vector store providers (Chroma, Qdrant, OpenSearch, etc.)
into a consistent format. Each vector database has unique characteristics and response formats -
this module abstracts those differences.

License: Apache 2.0
Ownership: Cloud Dog

Related Requirements: FR1.17, CM1.2
Related Architecture: CC2.1
"""

from typing import Dict, List, Any, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


class VectorStoreHarmonizer:
    """
    Harmonizes vector store responses across different providers.

    Different vector databases return results in different formats:
    - Chroma: Returns documents with distances and metadatas
    - Qdrant: Returns scored points with payloads
    - OpenSearch: Returns hits with _source and _score
    - PGVector: Returns rows with similarity scores
    - Weaviate: Returns objects with certainty scores

    This harmonizer converts all formats to a standard structure.
    """

    STANDARD_RESPONSE_SCHEMA = {
        "documents": List[Dict[str, Any]],  # List of document objects
        "metadata": Dict[str, Any],  # Query metadata (provider, timing, etc.)
        "total_results": int,  # Total number of results
        "provider": str,  # Vector store provider name
    }

    STANDARD_DOCUMENT_SCHEMA = {
        "id": str,  # Document ID
        "content": str,  # Document text content
        "score": float,  # Relevance/similarity score (0-1, higher is better)
        "metadata": Dict[str, Any],  # Document metadata
        "distance": Optional[float],  # Distance metric (if applicable)
    }

    @classmethod
    def harmonize_search_response(
        cls, provider: str, raw_response: Any, query: str, n_results: int
    ) -> Dict[str, Any]:
        """
        Harmonize search response from any vector store provider.

        Args:
            provider: Provider name (chroma, qdrant, opensearch, pgvector, weaviate)
            raw_response: Raw response from vector store
            query: Original search query
            n_results: Number of results requested

        Returns:
            Harmonized response in standard format
        """
        provider_lower = provider.lower()

        if provider_lower == "chroma":
            return cls._harmonize_chroma(raw_response, query, n_results)
        elif provider_lower == "qdrant":
            return cls._harmonize_qdrant(raw_response, query, n_results)
        elif provider_lower == "opensearch":
            return cls._harmonize_opensearch(raw_response, query, n_results)
        elif provider_lower == "pgvector":
            return cls._harmonize_pgvector(raw_response, query, n_results)
        elif provider_lower == "weaviate":
            return cls._harmonize_weaviate(raw_response, query, n_results)
        else:
            logger.warning(f"Unknown provider {provider}, using generic harmonization")
            return cls._harmonize_generic(raw_response, query, n_results, provider)

    @classmethod
    def _harmonize_chroma(cls, response: Any, query: str, n_results: int) -> Dict[str, Any]:
        """Harmonize Chroma response."""
        documents = []

        if isinstance(response, dict):
            ids = response.get("ids", [[]])[0] if response.get("ids") else []
            docs = response.get("documents", [[]])[0] if response.get("documents") else []
            distances = response.get("distances", [[]])[0] if response.get("distances") else []
            metadatas = response.get("metadatas", [[]])[0] if response.get("metadatas") else []

            for i, doc_id in enumerate(ids):
                # Chroma uses distance (lower is better), convert to score (higher is better)
                distance = distances[i] if i < len(distances) else None
                score = 1.0 / (1.0 + distance) if distance is not None else 0.5

                documents.append(
                    {
                        "id": str(doc_id),
                        "content": docs[i] if i < len(docs) else "",
                        "score": score,
                        "metadata": metadatas[i] if i < len(metadatas) else {},
                        "distance": distance,
                    }
                )

        return {
            "documents": documents,
            "metadata": {
                "query": query,
                "n_results": n_results,
                "provider": "chroma",
                "distance_metric": "l2",  # Chroma default
            },
            "total_results": len(documents),
            "provider": "chroma",
        }

    @classmethod
    def _harmonize_qdrant(cls, response: Any, query: str, n_results: int) -> Dict[str, Any]:
        """Harmonize Qdrant response."""
        documents = []

        if isinstance(response, list):
            for point in response:
                # Qdrant returns scored points
                score = point.get("score", 0.5)
                payload = point.get("payload", {})

                documents.append(
                    {
                        "id": str(point.get("id", "")),
                        "content": payload.get("content", payload.get("text", "")),
                        "score": score,
                        "metadata": {
                            k: v for k, v in payload.items() if k not in ["content", "text"]
                        },
                        "distance": None,  # Qdrant uses score directly
                    }
                )

        return {
            "documents": documents,
            "metadata": {
                "query": query,
                "n_results": n_results,
                "provider": "qdrant",
                "score_type": "cosine_similarity",
            },
            "total_results": len(documents),
            "provider": "qdrant",
        }

    @classmethod
    def _harmonize_opensearch(cls, response: Any, query: str, n_results: int) -> Dict[str, Any]:
        """Harmonize OpenSearch response."""
        documents = []

        if isinstance(response, dict):
            hits = response.get("hits", {}).get("hits", [])

            for hit in hits:
                # OpenSearch returns _score (higher is better)
                score = hit.get("_score", 0.0)
                source = hit.get("_source", {})

                # Normalize score to 0-1 range (OpenSearch scores can be > 1)
                normalized_score = min(score / 10.0, 1.0) if score > 0 else 0.0

                documents.append(
                    {
                        "id": str(hit.get("_id", "")),
                        "content": source.get("content", source.get("text", "")),
                        "score": normalized_score,
                        "metadata": {
                            k: v for k, v in source.items() if k not in ["content", "text"]
                        },
                        "distance": None,
                    }
                )

        return {
            "documents": documents,
            "metadata": {
                "query": query,
                "n_results": n_results,
                "provider": "opensearch",
                "score_type": "bm25",
            },
            "total_results": len(documents),
            "provider": "opensearch",
        }

    @classmethod
    def _harmonize_pgvector(cls, response: Any, query: str, n_results: int) -> Dict[str, Any]:
        """Harmonize PGVector response."""
        documents = []

        if isinstance(response, list):
            for row in response:
                # PGVector returns similarity score (0-1, higher is better)
                score = row.get("similarity", 0.5)

                documents.append(
                    {
                        "id": str(row.get("id", "")),
                        "content": row.get("content", row.get("text", "")),
                        "score": score,
                        "metadata": row.get("metadata", {}),
                        "distance": 1.0 - score if score is not None else None,
                    }
                )

        return {
            "documents": documents,
            "metadata": {
                "query": query,
                "n_results": n_results,
                "provider": "pgvector",
                "distance_metric": "cosine",
            },
            "total_results": len(documents),
            "provider": "pgvector",
        }

    @classmethod
    def _harmonize_weaviate(cls, response: Any, query: str, n_results: int) -> Dict[str, Any]:
        """Harmonize Weaviate response."""
        documents = []

        if isinstance(response, dict):
            objects = response.get("data", {}).get("Get", {})
            # Weaviate response structure varies by class name
            for class_name, items in objects.items():
                if isinstance(items, list):
                    for item in items:
                        # Weaviate uses certainty (0-1, higher is better)
                        certainty = item.get("_additional", {}).get("certainty", 0.5)

                        documents.append(
                            {
                                "id": item.get("_additional", {}).get("id", ""),
                                "content": item.get("content", item.get("text", "")),
                                "score": certainty,
                                "metadata": {
                                    k: v
                                    for k, v in item.items()
                                    if k not in ["content", "text", "_additional"]
                                },
                                "distance": 1.0 - certainty if certainty is not None else None,
                            }
                        )

        return {
            "documents": documents,
            "metadata": {
                "query": query,
                "n_results": n_results,
                "provider": "weaviate",
                "score_type": "certainty",
            },
            "total_results": len(documents),
            "provider": "weaviate",
        }

    @classmethod
    def _harmonize_generic(
        cls, response: Any, query: str, n_results: int, provider: str
    ) -> Dict[str, Any]:
        """Generic harmonization for unknown providers."""
        documents = []

        # Try to extract documents from common response structures
        if isinstance(response, list):
            for item in response:
                if isinstance(item, dict):
                    documents.append(
                        {
                            "id": str(item.get("id", item.get("_id", ""))),
                            "content": item.get(
                                "content", item.get("text", item.get("document", ""))
                            ),
                            "score": float(item.get("score", item.get("similarity", 0.5))),
                            "metadata": item.get("metadata", {}),
                            "distance": item.get("distance"),
                        }
                    )
        elif isinstance(response, dict):
            # Try common dict structures
            items = response.get("results", response.get("documents", response.get("hits", [])))
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        documents.append(
                            {
                                "id": str(item.get("id", "")),
                                "content": item.get("content", item.get("text", "")),
                                "score": float(item.get("score", 0.5)),
                                "metadata": item.get("metadata", {}),
                                "distance": item.get("distance"),
                            }
                        )

        return {
            "documents": documents,
            "metadata": {
                "query": query,
                "n_results": n_results,
                "provider": provider,
                "warning": "Generic harmonization used - provider not recognized",
            },
            "total_results": len(documents),
            "provider": provider,
        }

    @classmethod
    def compare_provider_characteristics(cls) -> Dict[str, Dict[str, Any]]:
        """
        Return characteristics of each vector store provider.

        Returns:
            Dict mapping provider name to its characteristics
        """
        return {
            "chroma": {
                "score_type": "distance",
                "score_range": "0-infinity (lower is better)",
                "distance_metrics": ["l2", "cosine", "ip"],
                "default_metric": "l2",
                "strengths": ["Easy to use", "Good for prototyping", "Local deployment"],
                "considerations": ["Distance-based scoring", "Limited scalability"],
            },
            "qdrant": {
                "score_type": "similarity",
                "score_range": "0-1 (higher is better)",
                "distance_metrics": ["cosine", "euclid", "dot"],
                "default_metric": "cosine",
                "strengths": ["High performance", "Rich filtering", "Production-ready"],
                "considerations": ["Requires separate service", "More complex setup"],
            },
            "opensearch": {
                "score_type": "relevance",
                "score_range": "0-infinity (higher is better)",
                "distance_metrics": ["l2", "cosine", "l1"],
                "default_metric": "l2",
                "strengths": ["Full-text search", "Mature ecosystem", "Hybrid search"],
                "considerations": [
                    "BM25 scoring differs from vector similarity",
                    "Resource intensive",
                ],
            },
            "pgvector": {
                "score_type": "similarity",
                "score_range": "0-1 (higher is better)",
                "distance_metrics": ["cosine", "l2", "inner_product"],
                "default_metric": "cosine",
                "strengths": ["PostgreSQL integration", "ACID compliance", "Familiar SQL"],
                "considerations": ["Performance at scale", "Index maintenance"],
            },
            "weaviate": {
                "score_type": "certainty",
                "score_range": "0-1 (higher is better)",
                "distance_metrics": ["cosine", "dot", "l2", "hamming", "manhattan"],
                "default_metric": "cosine",
                "strengths": ["GraphQL API", "Semantic search", "Multi-modal support"],
                "considerations": ["Unique query language", "Learning curve"],
            },
        }


def harmonize_vector_response(
    provider: str, response: Any, query: str, n_results: int
) -> Dict[str, Any]:
    """
    Convenience function to harmonize vector store responses.

    Args:
        provider: Vector store provider name
        response: Raw response from provider
        query: Original search query
        n_results: Number of results requested

    Returns:
        Harmonized response in standard format
    """
    return VectorStoreHarmonizer.harmonize_search_response(provider, response, query, n_results)
