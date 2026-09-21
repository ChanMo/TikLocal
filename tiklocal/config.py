from tiklocal.services.library import normalize_source_id


def normalize_media_sources(config, cli_sources=None, media_root=None):
    raw_sources = cli_sources or config.get('media_sources') or []
    sources = []
    if isinstance(raw_sources, dict):
        raw_sources = [{'id': key, 'path': value, 'name': key} for key, value in raw_sources.items()]
    if isinstance(raw_sources, list):
        for item in raw_sources:
            if not isinstance(item, dict):
                continue
            source_id = normalize_source_id(item.get('id') or item.get('name'))
            path = str(item.get('path') or '').strip()
            if not path:
                continue
            sources.append({
                'id': source_id,
                'name': str(item.get('name') or source_id).strip() or source_id,
                'path': path,
            })
    if media_root and all(item.get('id') != 'default' for item in sources):
        sources.insert(0, {'id': 'default', 'name': 'Default', 'path': str(media_root)})
    return sources


def similarity_enabled(experiments=None, embedding=None) -> bool:
    """Resolve the startup switch without importing vector runtime code."""
    from tiklocal.paths import get_embedding_config_path

    if experiments is not None and not isinstance(experiments, dict):
        raise ValueError('experiments must be a configuration object')
    similarity = (experiments or {}).get('similarity', {})
    if not isinstance(similarity, dict):
        raise ValueError('experiments.similarity must be a configuration object')
    if 'enabled' in similarity:
        if not isinstance(similarity['enabled'], bool):
            raise ValueError('experiments.similarity.enabled must be a boolean')
        return similarity['enabled']

    path = get_embedding_config_path()
    if not embedding and not path.exists():
        return False
    from tiklocal.experiments.similarity.config import EmbeddingConfigStore, validate_embedding_config

    custom = EmbeddingConfigStore(path).get()
    configured, error = validate_embedding_config(embedding or {}, partial=True)
    return bool((custom or (configured if not error else {}) or {}).get('enabled', False))
