import asyncio
import logging

from app.crypto import TokenCipher
from app.database import Database
from app.linkedin import LinkedInClient
from app.repository import SocialRepository


async def refresh_tokens_forever(database: Database, cipher: TokenCipher) -> None:
    settings = database.settings
    linkedin = LinkedInClient(settings)
    while True:
        try:
            async with database.transaction() as conn:
                repo = SocialRepository(conn)
                rows = await repo.connections_needing_refresh(settings.token_refresh_leeway_seconds)
                for row in rows:
                    refresh_token = cipher.decrypt(row["encrypted_refresh_token"])
                    if not refresh_token:
                        continue
                    token_data = await linkedin.refresh_access_token(refresh_token)
                    await repo.update_connection_tokens(
                        row["id"],
                        cipher.encrypt(token_data["access_token"]),
                        cipher.encrypt(token_data.get("refresh_token")) if token_data.get("refresh_token") else None,
                        token_data.get("expires_in"),
                    )
        except Exception as exc:
            logging.warning("LinkedIn token refresh cycle failed: %s", exc)
        await asyncio.sleep(settings.token_refresh_interval_seconds)

