import hashlib
from unittest.mock import AsyncMock, patch

import pytest


class TestEmbeddingCache:
    @pytest.mark.asyncio
    async def test_cache_hit(self, mock_kb_path):
        from duckkb.utils.embedding import get_embeddings

        text = "test text for caching"
        text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
        cached_embedding = [0.1] * 1536

        with patch("duckkb.utils.embedding.get_openai_client") as mock_client:
            with patch("duckkb.utils.embedding._get_cached_embeddings_batch") as mock_cache:
                mock_cache.return_value = {text_hash: cached_embedding}

                result = await get_embeddings([text])

                assert result == [cached_embedding]
                mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss(self, mock_kb_path):
        from duckkb.utils.embedding import get_embeddings

        text = "new text not in cache"
        new_embedding = [0.2] * 1536

        async def side_effect(*args, **kwargs):
            mock_response = AsyncMock()
            mock_data = AsyncMock()
            mock_data.embedding = new_embedding
            mock_response.data = [mock_data]
            return mock_response

        mock_client = AsyncMock()
        mock_client.embeddings.create.side_effect = side_effect

        with patch("duckkb.utils.embedding.get_openai_client", return_value=mock_client):
            with patch("duckkb.utils.embedding._get_cached_embeddings_batch", return_value={}):
                with patch("duckkb.utils.embedding._cache_embeddings_batch") as mock_cache_store:
                    result = await get_embeddings([text])

                    assert result == [new_embedding]
                    mock_cache_store.assert_called_once()

    @pytest.mark.asyncio
    async def test_batch_embeddings_partial_cache(self, mock_kb_path):
        from duckkb.utils.embedding import get_embeddings

        texts = ["cached text", "new text 1", "new text 2"]
        cached_hash = hashlib.md5(b"cached text").hexdigest()
        cached_embedding = [0.1] * 1536
        new_embedding_1 = [0.2] * 1536
        new_embedding_2 = [0.3] * 1536

        async def side_effect(*args, **kwargs):
            mock_response = AsyncMock()
            mock_data_list = []
            embeddings = [new_embedding_1, new_embedding_2]
            for emb in embeddings:
                d = AsyncMock()
                d.embedding = emb
                mock_data_list.append(d)
            mock_response.data = mock_data_list
            return mock_response

        mock_client = AsyncMock()
        mock_client.embeddings.create.side_effect = side_effect

        with patch("duckkb.utils.embedding.get_openai_client", return_value=mock_client):
            with patch("duckkb.utils.embedding._get_cached_embeddings_batch") as mock_cache_get:
                mock_cache_get.return_value = {cached_hash: cached_embedding}
                with patch("duckkb.utils.embedding._cache_embeddings_batch"):
                    result = await get_embeddings(texts)

                    assert len(result) == 3
                    assert result[0] == cached_embedding
                    assert result[1] == new_embedding_1
                    assert result[2] == new_embedding_2

    @pytest.mark.asyncio
    async def test_empty_input(self, mock_kb_path):
        from duckkb.utils.embedding import get_embeddings

        result = await get_embeddings([])
        assert result == []

    @pytest.mark.asyncio
    async def test_single_embedding_wrapper(self, mock_kb_path):
        from duckkb.utils.embedding import get_embedding

        text = "single text"
        embedding = [0.5] * 1536

        with patch("duckkb.utils.embedding.get_embeddings") as mock_get_embeddings:
            mock_get_embeddings.return_value = [embedding]
            result = await get_embedding(text)

            assert result == embedding
            mock_get_embeddings.assert_called_once_with([text])
