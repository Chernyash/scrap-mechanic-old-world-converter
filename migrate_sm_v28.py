"""
Migrate Scrap Mechanic Survival save from savegameversion 27 -> 28 (1.0).

Observed format deltas vs a fresh 1.0 world:
  - Game.savegameversion: 27 -> 28
  - Game.uniqueIds: BE u32 count 16->17, append 0x40000000
  - ScriptableObject table: add worldId INTEGER + index
  - ScriptableObject.data: insert worldId as bytes FF FE (65534 / noWorld) after 7-byte header
  - ChildShape.data: append 0x00
  - Unit.data: append 0x00
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path


NO_WORLD = 65534  # sm.world.ids.noWorld
NO_WORLD_BYTES = b"\xff\xfe"  # byte order as stored in 1.0 blobs
TARGET_VERSION = 28
UNIQUE_IDS_NEW_COUNTER = 0x40000000
BATCH = 5000


def migrate_unique_ids(blob: bytes) -> bytes:
    if blob is None or len(blob) < 4 or len(blob) % 4 != 0:
        raise ValueError(f"unexpected uniqueIds length: {0 if blob is None else len(blob)}")
    count = int.from_bytes(blob[:4], "big")
    values = blob[4:]
    n_values = len(values) // 4
    if count != n_values:
        raise ValueError(f"uniqueIds count mismatch: header={count} values={n_values}")
    if count == 17 and values.endswith(UNIQUE_IDS_NEW_COUNTER.to_bytes(4, "big")):
        return blob
    if count != 16:
        raise ValueError(f"expected uniqueIds count 16 for v27, got {count}")
    return (17).to_bytes(4, "big") + values + UNIQUE_IDS_NEW_COUNTER.to_bytes(4, "big")


def migrate_scriptable_object_blob(data: bytes) -> bytes:
    if data is None:
        raise ValueError("ScriptableObject data is NULL")
    # already migrated (v28 sample length is 27)
    if len(data) == 27 and data[7:9] == NO_WORLD_BYTES:
        return data
    if len(data) < 7:
        raise ValueError(f"ScriptableObject blob too short: {len(data)}")
    return data[:7] + NO_WORLD_BYTES + data[7:]


def append_zero_where(cur: sqlite3.Cursor, table: str, old_lengths: set[int]) -> int:
    """Append 0x00 to BLOB rows with given lengths. Done in Python to avoid SQLite || text coercion."""
    total = 0
    ids = [
        r[0]
        for r in cur.execute(
            f"SELECT id FROM [{table}] WHERE length(data) IN ({','.join(str(x) for x in sorted(old_lengths))})"
        )
    ]
    for i in range(0, len(ids), BATCH):
        chunk = ids[i : i + BATCH]
        qmarks = ",".join("?" * len(chunk))
        rows = cur.execute(
            f"SELECT id, data FROM [{table}] WHERE id IN ({qmarks})", chunk
        ).fetchall()
        updates = []
        for rid, data in rows:
            if not isinstance(data, (bytes, bytearray, memoryview)):
                raise TypeError(f"{table}.id={rid} data is {type(data)}, not blob")
            b = bytes(data)
            if len(b) in old_lengths:
                updates.append((b + b"\x00", rid))
        cur.executemany(f"UPDATE [{table}] SET data = ? WHERE id = ?", updates)
        total += len(updates)
        print(f"  {table}: {total}/{len(ids)}")
    return total


def migrate_db(src: Path, dst: Path) -> None:
    if dst.exists():
        dst.unlink()
    shutil.copy2(src, dst)

    con = sqlite3.connect(str(dst))
    con.execute("PRAGMA foreign_keys = OFF")
    con.execute("PRAGMA journal_mode = OFF")
    con.execute("PRAGMA synchronous = OFF")
    cur = con.cursor()

    row = cur.execute("SELECT savegameversion, uniqueIds FROM Game").fetchone()
    if row is None:
        raise RuntimeError("Game table is empty")
    version, unique_ids = row
    print(f"source savegameversion={version}")

    new_uids = migrate_unique_ids(unique_ids)
    cur.execute(
        "UPDATE Game SET savegameversion = ?, uniqueIds = ?",
        (TARGET_VERSION, new_uids),
    )
    print(f"uniqueIds {len(unique_ids)} -> {len(new_uids)} bytes")

    print("ChildShape...")
    n_cs = append_zero_where(cur, "ChildShape", {42, 47})
    print(f"ChildShape appended byte: {n_cs} rows")

    print("Unit...")
    n_unit = append_zero_where(cur, "Unit", {64})
    print(f"Unit appended byte: {n_unit} rows")

    cols = [r[1] for r in cur.execute("PRAGMA table_info(ScriptableObject)")]
    if "worldId" not in cols:
        print("recreating ScriptableObject with worldId column")
        rows = cur.execute("SELECT id, data FROM ScriptableObject").fetchall()
        cur.execute("ALTER TABLE ScriptableObject RENAME TO ScriptableObject_old")
        cur.execute(
            """
            CREATE TABLE ScriptableObject(
                id INTEGER PRIMARY KEY,
                worldId INTEGER,
                data BLOB
            )
            """
        )
        for sid, data in rows:
            new_data = migrate_scriptable_object_blob(bytes(data))
            cur.execute(
                "INSERT INTO ScriptableObject(id, worldId, data) VALUES (?, ?, ?)",
                (sid, NO_WORLD, new_data),
            )
        cur.execute("DROP TABLE ScriptableObject_old")
        print(f"ScriptableObject migrated rows: {len(rows)}")
    else:
        rows = cur.execute("SELECT id, worldId, data FROM ScriptableObject").fetchall()
        fixed = 0
        for sid, world_id, data in rows:
            new_data = migrate_scriptable_object_blob(bytes(data))
            if new_data != bytes(data) or world_id != NO_WORLD:
                cur.execute(
                    "UPDATE ScriptableObject SET worldId = ?, data = ? WHERE id = ?",
                    (NO_WORLD, new_data, sid),
                )
                fixed += 1
        print(f"ScriptableObject blob fixes: {fixed}")

    cur.execute(
        "CREATE INDEX IF NOT EXISTS ScriptableObject_idx_world "
        "ON ScriptableObject(worldId)"
    )

    con.commit()

    v = cur.execute("SELECT savegameversion FROM Game").fetchone()[0]
    so_cols = [r[1] for r in cur.execute("PRAGMA table_info(ScriptableObject)")]
    cs_lens = cur.execute(
        "SELECT length(data), count(*) FROM ChildShape GROUP BY 1 ORDER BY 1"
    ).fetchall()
    unit_lens = cur.execute(
        "SELECT length(data), count(*) FROM Unit GROUP BY 1 ORDER BY 1"
    ).fetchall()
    so = list(cur.execute("SELECT id, worldId, length(data), hex(data) FROM ScriptableObject"))
    sample_cs = cur.execute(
        "SELECT id, length(data), hex(data) FROM ChildShape LIMIT 2"
    ).fetchall()
    uids = cur.execute("SELECT length(uniqueIds), hex(substr(uniqueIds,1,8)), hex(substr(uniqueIds,-4,4)) FROM Game").fetchone()

    print("---- verify ----")
    print("savegameversion:", v)
    print("ScriptableObject cols:", so_cols)
    print("ChildShape lengths:", cs_lens)
    print("Unit lengths:", unit_lens)
    print("ChildShape sample:", sample_cs)
    print("ScriptableObject:", so)
    print("uniqueIds:", uids)

    # compare against reference new-world shapes of same hdr
    ref = sqlite3.connect(r"C:\Users\root\Desktop\test\test123.db")
    ref_so = ref.execute("SELECT hex(data) FROM ScriptableObject LIMIT 1").fetchone()[0]
    print("ref ScriptableObject starts:", ref_so[:28], "has FFFE at +7:", ref_so[14:18])
    print("our ScriptableObject:", so[0][3] if so else None)
    ref.close()

    con.close()
    print(f"wrote {dst} ({dst.stat().st_size} bytes)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path)
    ap.add_argument("dst", type=Path)
    args = ap.parse_args()
    migrate_db(args.src, args.dst)
    return 0


if __name__ == "__main__":
    sys.exit(main())
