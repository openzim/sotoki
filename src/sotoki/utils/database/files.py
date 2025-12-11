import json
from dataclasses import dataclass

import snappy

from sotoki.utils.shared import shared


@dataclass(kw_only=True)
class File:
    url: str
    zim_path: str
    download_attempts: int


class FileDatabase:

    def __init__(self, hostname: str):
        self.hostname = hostname

    @property
    def _list_name(self) -> str:
        return f"{self.hostname}-files"

    def pop(self) -> File | None:
        file = shared.database.safe_command("rpop", self._list_name)
        if not file:
            return None
        file = json.loads(snappy.decompress(file))
        return File(url=file[0], zim_path=file[1], download_attempts=file[2])

    def push(self, file: File):
        file_bytes = snappy.compress(
            json.dumps(
                (
                    file.url,
                    file.zim_path,
                    file.download_attempts,
                )
            )
        )

        shared.database.safe_command("lpush", self._list_name, file_bytes)

    def len(self) -> int:
        return shared.database.safe_command("llen", self._list_name)

    def flush(self):
        shared.database.safe_command("delete", self._list_name)
