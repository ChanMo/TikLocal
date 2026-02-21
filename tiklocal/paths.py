import os
from pathlib import Path


def get_data_dir() -> Path:
    """Return the global data directory for TikLocal.
    Default to ~/.tiklocal unless TIKLOCAL_INSTANCE is set.
    """
    base = os.environ.get('TIKLOCAL_INSTANCE')
    if base:
        p = Path(base).expanduser()
    else:
        p = Path.home() / '.tiklocal'
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_thumbnails_dir() -> Path:
    d = get_data_dir() / 'thumbnails'
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_thumbs_map_path() -> Path:
    return get_data_dir() / 'thumbs.json'


def get_metadata_path() -> Path:
    return get_data_dir() / 'metadata.json'


def get_prompt_config_path() -> Path:
    return get_data_dir() / 'prompt_config.json'


def get_llm_config_path() -> Path:
    return get_data_dir() / 'llm_config.json'


def get_download_config_path() -> Path:
    return get_data_dir() / 'download_config.json'


def get_download_jobs_path() -> Path:
    return get_data_dir() / 'download_jobs.json'


def get_download_sources_path() -> Path:
    return get_data_dir() / 'download_sources.json'
