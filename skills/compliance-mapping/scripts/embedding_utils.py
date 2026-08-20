#!/usr/bin/env python3
# Copyright OSCAL Compass Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Shared embedding + ANN search helpers.

Uses sentence-transformers for embeddings and FAISS for approximate
nearest-neighbor search when available. Falls back to a pure-numpy
brute-force cosine search if faiss is not installed, so the pipeline
never hard-depends on a native extension being present.

No external API keys are required anywhere in this module.
"""
import hashlib
import json
import os
import sys

import numpy as np

DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"

_model_cache = {}


def _get_model(model_name=DEFAULT_MODEL_NAME):
    if model_name in _model_cache:
        return _model_cache[model_name]
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name)
    _model_cache[model_name] = model
    return model


def text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cache_key(model_name, text):
    return hashlib.sha256(f"{model_name}::{text}".encode("utf-8")).hexdigest()


def load_embedding_cache(cache_path):
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return {k: np.array(v, dtype=np.float32) for k, v in raw.items()}
    return {}


def save_embedding_cache(cache_path, cache):
    os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
    serializable = {k: v.tolist() for k, v in cache.items()}
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(serializable, f)


def embed_texts(items, model_name=DEFAULT_MODEL_NAME, cache_path=None, batch_size=64):
    """items: list of (id, text). Returns dict id -> np.ndarray (float32, L2-normalized)."""
    cache = load_embedding_cache(cache_path) if cache_path else {}
    result = {}
    to_compute_ids = []
    to_compute_texts = []

    for item_id, text in items:
        key = cache_key(model_name, text)
        if key in cache:
            result[item_id] = cache[key]
        else:
            to_compute_ids.append(item_id)
            to_compute_texts.append(text)

    if to_compute_texts:
        model = _get_model(model_name)
        vectors = model.encode(
            to_compute_texts,
            batch_size=batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        for item_id, text, vec in zip(to_compute_ids, to_compute_texts, vectors):
            vec = np.asarray(vec, dtype=np.float32)
            result[item_id] = vec
            if cache_path:
                cache[cache_key(model_name, text)] = vec

    if cache_path and to_compute_texts:
        save_embedding_cache(cache_path, cache)

    return result


class ANNIndex:
    """Cosine-similarity top-K search. Uses FAISS if installed, else numpy brute force."""

    def __init__(self, ids, vectors):
        self.ids = list(ids)
        self.matrix = np.stack(vectors).astype(np.float32) if vectors else np.zeros((0, 0), dtype=np.float32)
        self._faiss_index = None
        self._try_build_faiss()

    def _try_build_faiss(self):
        if self.matrix.shape[0] == 0:
            return
        try:
            import faiss
        except ImportError:
            return
        dim = self.matrix.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(self.matrix)
        self._faiss_index = index

    def search(self, query_vector, k=20):
        """Returns list of (id, score) sorted by descending cosine similarity."""
        if self.matrix.shape[0] == 0:
            return []
        k = min(k, self.matrix.shape[0])
        query_vector = np.asarray(query_vector, dtype=np.float32).reshape(1, -1)

        if self._faiss_index is not None:
            scores, indices = self._faiss_index.search(query_vector, k)
            return [
                (self.ids[idx], float(score))
                for idx, score in zip(indices[0], scores[0])
                if idx != -1
            ]

        sims = (self.matrix @ query_vector.T).flatten()
        top_idx = np.argpartition(-sims, k - 1)[:k]
        top_idx = top_idx[np.argsort(-sims[top_idx])]
        return [(self.ids[i], float(sims[i])) for i in top_idx]


def backend_name():
    try:
        import faiss  # noqa: F401

        return "faiss"
    except ImportError:
        return "numpy-bruteforce"


if __name__ == "__main__":
    print(f"embedding backend model={DEFAULT_MODEL_NAME}", file=sys.stderr)
    print(f"ann backend={backend_name()}", file=sys.stderr)
