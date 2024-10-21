import logging
from requests import sessions
from datetime import datetime, timedelta
import time

import json

logger = logging.getLogger("script.ballchasing_api")

logging.basicConfig(
    filename="../../logs/rlis.log",
    encoding="utf-8",
    datefmt="%Y-%m-%d %H:%M:%S",
    format="[%(asctime)s] [%(levelname)-8s] %(name)s: %(message)s",
    level=logging.DEBUG,
)


class API:
    def __init__(self, api_key):

        self.api_key = api_key

        # Establish a session to reuse TCP connection
        self._session = sessions.Session()

        logger.info("Established session with ballchasing.com API")

    def filter(self, start: datetime, end: datetime, players: list[tuple[int, int]]) -> dict:

        # Base url only requires private match playlist type
        url = "https://ballchasing.com/api/replays?playlist=private"

        # Add player constraints
        for player in players:
            url += f"&player-id={player[0]}:{player[1]}"

        time_format = "%Y-%m-%dT%H:%M:00Z"
        start_str = start.strftime(time_format)
        end_str = end.strftime(time_format)
        # Add time constraints
        url += f"&created-after={start_str}&created-before={end_str}"

        r = self._session.get(url, headers={"Authorization": self.api_key})

        if r.status_code == 200:
            logger.info(f"Call returned {r.status_code}")

            data = r.json()

            # Further filter the results to only include those with exactly the specified players
            data["list"] = [
                game
                for game in data["list"]
                if len(game["blue"]["players"]) + len(game["orange"]["players"]) == len(players)
            ]

            data["count"] = len(data["list"])

            return data

        elif r.status_code == 429:
            logger.warning(f"Call returned {r.status_code}, slow down requests")
            return r.json()

        else:
            logger.error(f"Call returned {r.status_code}, failing")
            raise APIError(f"status code {r.status_code}")

    def get(self, id: str) -> dict:
        url = f"https://ballchasing.com/api/replays/{id}"

        r = self._session.get(url, headers={"Authorization": self.api_key})

        if r.status_code == 200:
            logger.info(f"Call returned {r.status_code}")

            return r.json()

        elif r.status_code == 429:
            logger.warning(f"Call returned {r.status_code}, slow down requests")
            return r.json()

        else:
            logger.error(f"Call returned {r.status_code}, failing")
            raise APIError(f"status code {r.status_code}")


class APIError(Exception):

    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return f"APIError: {self.msg}"
