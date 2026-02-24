import asyncio
import hashlib
from pathlib import Path

import orjson

from duckkb.config import settings
from duckkb.constants import BUILD_DIR_NAME, DATA_DIR_NAME, SYS_SEARCH_TABLE
from duckkb.db import get_db
from duckkb.logger import logger
from duckkb.utils.embedding import get_embeddings
from duckkb.utils.text import segment_text

SYNC_STATE_FILE = "sync_state.json"


async def sync_knowledge_base(kb_path: Path):
    """Sync the knowledge base from JSONL files to DuckDB."""
    # Warmup jieba in main thread to avoid race conditions or lag in threads
    segment_text("")

    data_dir = kb_path / DATA_DIR_NAME
    if not data_dir.exists():
        logger.warning(f"Data directory {data_dir} does not exist.")
        return

    # Load sync state
    state_file = kb_path / BUILD_DIR_NAME / SYNC_STATE_FILE
    sync_state = {}
    if state_file.exists():
        try:
            sync_state = orjson.loads(state_file.read_bytes())
        except Exception:
            logger.warning("Failed to load sync state, resetting.")

    # Iterate jsonl files
    for file_path in data_dir.glob("*.jsonl"):
        table_name = file_path.stem
        mtime = file_path.stat().st_mtime

        # Check if file modified
        if sync_state.get(table_name) == mtime:
            logger.debug(f"Skipping {table_name}, up to date.")
            continue

        logger.info(f"Syncing table {table_name}...")

        try:
            await _process_file(file_path, table_name)
            # Update state only on success
            sync_state[table_name] = mtime
        except Exception as e:
            logger.error(f"Failed to sync {table_name}: {e}")

    # Save sync state
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_bytes(orjson.dumps(sync_state))

    # Ensure FTS index
    try:
        with get_db(read_only=False) as conn:
            # PRAGMA create_fts_index is idempotent in newer DuckDB versions,
            # or we can wrap it. But usually it's fine to call.
            # If table is empty, it might warn/fail.
            # Use 'rowid' as the key column for FTS to handle non-unique ref_ids
            conn.execute(
                f"PRAGMA create_fts_index('{SYS_SEARCH_TABLE}', 'rowid', 'segmented_text')"
            )
    except Exception as e:
        logger.warning(f"FTS index creation/refresh failed: {e}")

    # Trigger GC
    await clean_cache()


async def clean_cache():
    """Clean up unused vector cache entries older than 30 days."""
    logger.info("Running cache GC...")
    try:
        # Use asyncio.to_thread for blocking DB op
        await asyncio.to_thread(_execute_gc)
    except Exception as e:
        logger.error(f"Cache GC failed: {e}")


def _execute_gc():
    with get_db(read_only=False) as conn:
        conn.execute("DELETE FROM _sys_cache WHERE last_used < current_timestamp - INTERVAL 30 DAY")


def _read_records(file_path: Path) -> list[dict]:
    """Read and parse JSONL file."""
    records = []
    try:
        content = file_path.read_bytes()
        for line in content.splitlines():
            if not line.strip():
                continue
            records.append(orjson.loads(line))
    except Exception as e:
        raise ValueError(f"Failed to parse {file_path}: {e}")
    return records


async def _process_file(file_path: Path, table_name: str):
    # 1. Read all records asynchronously (I/O bound)
    try:
        records = await asyncio.to_thread(_read_records, file_path)
    except Exception as e:
        raise ValueError(f"Failed to read {file_path}: {e}")

    # 2. Collect texts for embedding
    # Format: (record_idx, field_key, text)
    embedding_requests = []

    for i, record in enumerate(records):
        ref_id = str(record.get("id", ""))
        if not ref_id:
            continue

        for key, value in record.items():
            if isinstance(value, str) and value.strip():
                embedding_requests.append((i, key, value))

    if not embedding_requests:
        return

    texts_to_embed = [req[2] for req in embedding_requests]

    # 3. Batch Embedding (I/O bound, concurrency handled inside)
    try:
        embeddings = await get_embeddings(texts_to_embed)
    except Exception as e:
        logger.error(f"Failed to get embeddings for {table_name}: {e}")
        # If embedding fails completely, we skip the file to avoid partial state?
        # Or just return, meaning no rows inserted.
        return

    # 4. Parallel Segmentation (CPU bound)
    # Use default executor (ThreadPool) which releases GIL for many C-extensions
    # jieba is pure python but might be slow. ProcessPool is better for CPU bound
    # but requires pickling and overhead. ThreadPool is a good start.
    loop = asyncio.get_running_loop()
    try:
        segmented_texts = await asyncio.gather(
            *[loop.run_in_executor(None, segment_text, text) for text in texts_to_embed]
        )
    except Exception as e:
        logger.error(f"Failed to segment text: {e}")
        return

    # 5. Assemble Rows
    rows_to_insert: list[tuple] = []

    for idx, (original_idx, key, text) in enumerate(embedding_requests):
        record = records[original_idx]
        ref_id = str(record.get("id", ""))

        # Check if embedding exists (it should match index)
        if idx >= len(embeddings) or not embeddings[idx]:
            continue

        embedding_id = hashlib.md5(text.encode("utf-8")).hexdigest()
        metadata_json = orjson.dumps(record).decode("utf-8")

        rows_to_insert.append(
            (
                ref_id,
                table_name,
                key,
                segmented_texts[idx],
                embedding_id,
                metadata_json,
                1.0,  # priority
            )
        )

    # 6. Bulk Insert
    if rows_to_insert:
        await asyncio.to_thread(_bulk_insert, table_name, rows_to_insert)


def _bulk_insert(table_name: str, rows: list[tuple]):
    with get_db(read_only=False) as conn:
        conn.execute("BEGIN TRANSACTION")
        try:
            # 1. Clear old records for this table
            conn.execute(f"DELETE FROM {SYS_SEARCH_TABLE} WHERE source_table = ?", [table_name])

            # 2. Insert new records
            # Schema: (ref_id, source_table, source_field, segmented_text, embedding_id, metadata, priority_weight)
            conn.executemany(f"INSERT INTO {SYS_SEARCH_TABLE} VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
            conn.execute("COMMIT")
            logger.info(f"Inserted {len(rows)} rows for {table_name}")
        except Exception as e:
            conn.execute("ROLLBACK")
            raise e


async def validate_and_import(table_name: str, temp_file_path: Path) -> str:
    """
    Validate temp file and move to data dir.

    Args:
        table_name: The target table name (without .jsonl).
        temp_file_path: Path to the temporary JSONL file.
    """
    if not temp_file_path.exists():
        raise FileNotFoundError(f"File {temp_file_path} not found")

    # 1. Validation
    errors = []
    valid_count = 0

    try:
        content = await asyncio.to_thread(temp_file_path.read_bytes)
        lines = content.splitlines()

        for i, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                record = orjson.loads(line)
                if not isinstance(record, dict):
                    errors.append(f"Line {i}: Record must be a JSON object")
                    continue

                # Enforce 'id' field as per our convention
                if "id" not in record:
                    errors.append(f"Line {i}: Missing required field 'id'")

                valid_count += 1

            except orjson.JSONDecodeError:
                errors.append(f"Line {i}: Invalid JSON format")

    except Exception as e:
        raise ValueError(f"Failed to read file: {e}")

    if errors:
        # Return up to 5 errors to avoid flooding
        error_msg = f"Found {len(errors)} errors:\n" + "\n".join(errors[:5])
        if len(errors) > 5:
            error_msg += "\n..."
        raise ValueError(error_msg)

    # 2. Merge to data/ (Atomic)
    target_path = settings.KB_PATH / DATA_DIR_NAME / f"{table_name}.jsonl"
    target_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Atomic Merge: Read existing -> Append new -> Write temp -> Rename
        final_content = b""
        if target_path.exists():
            final_content = await asyncio.to_thread(target_path.read_bytes)
            if final_content and not final_content.endswith(b"\n"):
                final_content += b"\n"

        # temp_file_path already validated
        new_content = await asyncio.to_thread(temp_file_path.read_bytes)
        final_content += new_content

        # Write to a staging file in target dir to ensure same filesystem for atomic rename
        staging_path = target_path.with_suffix(".jsonl.staging")
        await asyncio.to_thread(staging_path.write_bytes, final_content)

        # Atomic rename
        staging_path.replace(target_path)

        # Cleanup temp import file
        try:
            temp_file_path.unlink()
        except:
            pass

    except Exception as e:
        raise OSError(f"Failed to merge file to {target_path}: {e}")

    # 3. Trigger Sync
    logger.info(f"Imported {table_name}, triggering sync...")
    await sync_knowledge_base(settings.KB_PATH)

    return f"Successfully imported {valid_count} records to {table_name}"
