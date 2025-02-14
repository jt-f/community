import asyncio
import logging

class Community:
    async def start(self):
        """Start the community"""
        self.running = True
        logging.debug("Community started")
        # Start the message loop as a background task
        asyncio.create_task(self.message_loop())
        logger.debug("Message loop started as background task") 