from typing import Annotated

from fastapi import Depends

from elenchos.config import ElenchosSettings, get_settings

SettingsDep = Annotated[ElenchosSettings, Depends(get_settings)]
