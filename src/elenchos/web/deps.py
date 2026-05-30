from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from elenchos.config import ElenchosSettings


@lru_cache
def get_settings() -> ElenchosSettings:
    return ElenchosSettings()


SettingsDep = Annotated[ElenchosSettings, Depends(get_settings)]
