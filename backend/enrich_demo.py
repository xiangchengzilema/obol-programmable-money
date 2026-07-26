"""
Non-destructive marketplace enrichment.

Adds any missing seeded creators/articles to the current DB without deleting
agent runs, receipts, or live Arc evidence.
"""
import time

from db import init_db, get_db
from seed import CREATORS, ARTICLES


def enrich():
    init_db()
    conn = get_db()
    cur = conn.cursor()
    now = time.time()

    creator_ids = {}
    for offset, (name, addr) in enumerate(CREATORS):
        row = cur.execute("SELECT id FROM creators WHERE name=?", (name,)).fetchone()
        if row:
            creator_ids[name] = row["id"]
            continue
        cur.execute("INSERT INTO creators(name, payout_address, created_at) VALUES(?,?,?)",
                    (name, addr, now - (len(CREATORS) - offset) * 3600))
        creator_ids[name] = cur.lastrowid

    added_articles = 0
    for offset, (creator_idx, title, summary, content, price, tags) in enumerate(ARTICLES):
        exists = cur.execute("SELECT 1 FROM articles WHERE title=?", (title,)).fetchone()
        if exists:
            continue
        creator_name = CREATORS[creator_idx][0]
        cur.execute("""INSERT INTO articles(creator_id, title, summary, content, price_usdc, tags, created_at)
                       VALUES(?,?,?,?,?,?,?)""",
                    (creator_ids[creator_name], title, summary, content, price, tags,
                     now - (len(ARTICLES) - offset) * 1800))
        added_articles += 1

    conn.commit()
    totals = {
        "creators": cur.execute("SELECT COUNT(*) FROM creators").fetchone()[0],
        "articles": cur.execute("SELECT COUNT(*) FROM articles").fetchone()[0],
        "receipts": cur.execute("SELECT COUNT(*) FROM receipts").fetchone()[0],
        "added_articles": added_articles,
    }
    conn.close()
    return totals


if __name__ == "__main__":
    print(enrich())
