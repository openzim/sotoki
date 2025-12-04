import dataclasses
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from zimscraperlib.logging import DEFAULT_FORMAT_WITH_THREADS, getLogger

from sotoki.constants import NAME


@dataclass(kw_only=True)
class Context:
    """Class holding every contextual / configuration bits which can be moved

    Used to easily pass information around in the scraper. One singleton instance is
    always available.
    """

    # singleton instance
    _instance: Context | None = None

    # StackExchange domain to ZIM and mirror to download archives
    domain: str
    mirror: str

    # URL to redis instance
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379")

    # ZIM metadata
    name: str | None = None
    title: str
    description: str
    long_description: str | None = None
    creator: str = "Stack Exchange"
    publisher: str = "openZIM"
    fname: str = ""
    tags: list[str] = field(default_factory=list)
    flavour: str | None = None

    # customization
    favicon: str | None = ""

    # filesystem
    output_dir: Path = Path(os.getenv("SOTOKI_OUTPUT", "./output"))
    tmp_dir: Path = Path(os.getenv("TMPDIR", "./build"))

    # performances
    nb_threads: int = 1
    s3_url_with_credentials: str | None = ""

    # censorship
    censor_words_list: str = ""
    without_images: bool = False
    without_user_profiles: bool = False
    without_external_links: bool = False
    without_unanswered: bool = False
    without_users_links: bool = False
    without_names: bool = False

    # debug/devel
    keep_build_dir: bool = False
    keep_redis: bool = False
    debug: bool = False
    prepare_only: bool = False
    keep_intermediate_files: bool = False
    stats_filename: Path | None = None
    build_dir_is_tmp_dir: bool = False
    defrag_redis: str | None = None
    open_shell: bool = False
    skip_tags_meta: bool = False
    skip_questions_meta: bool = False
    skip_users: bool = False

    # logger to use everywhere (do not mind about mutability, we want to reuse same
    # logger everywhere)
    logger: logging.Logger = getLogger(  # noqa: RUF009
        NAME, level=logging.DEBUG, log_format=DEFAULT_FORMAT_WITH_THREADS
    )

    @classmethod
    def setup(cls, **kwargs: Any):
        new_instance = cls(**kwargs)
        if cls._instance:
            # replace values 'in-place' so that we do not change the Context object
            # which might be already imported in some modules
            for field in dataclasses.fields(new_instance):
                cls._instance.__setattr__(
                    field.name, new_instance.__getattribute__(field.name)
                )
        else:
            cls._instance = new_instance

    @classmethod
    def get(cls) -> Context:
        if not cls._instance:
            raise OSError("Uninitialized context")  # pragma: no cover
        return cls._instance

    @property
    def redis_pid(self):
        if not self.defrag_redis:
            return None
        if self.defrag_redis == "service":
            return self.defrag_redis
        if self.defrag_redis.isnumeric():
            return int(self.defrag_redis)
        m = re.match(r"^ENV:(?P<name>.+)", self.defrag_redis)
        if m:
            env_name = m.groupdict().get("name")
            if env_name:
                try:
                    env_value = os.getenv(env_name)
                    if env_value:
                        return int(env_value)
                except Exception:
                    return None
        return None
