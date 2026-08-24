
                last_seen TEXT
            )
        """)
        await db.commit()

async def load_user(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT first_name, username, gender FROM users WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
            if row:
