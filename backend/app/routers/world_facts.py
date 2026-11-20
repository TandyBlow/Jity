"""Read-only narration facts for one committed point.

This route exposes the frozen adapter to the world page so the page no longer needs a second process.
Nothing here writes: the adapter opens the database read-only and the route only serialises its result.

The adapter lives in the components experiment tree, not in this backend, so it is loaded from the path
in WORLD_FACTS_ADAPTER. When that path is unset or cannot be imported the route answers 503 instead of
inventing facts - a deployment mistake must not look like a quiet turn.
"""
import importlib.util
import os
import pathlib

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix='/world/facts', tags=['world-facts'])
_CACHE = {'module': None, 'path': None, 'error': None}


def _adapter():
    path = os.environ.get('WORLD_FACTS_ADAPTER')
    if not path:
        raise HTTPException(status_code=503, detail='WORLD_FACTS_ADAPTER is not set')
    if _CACHE['module'] is not None and _CACHE['path'] == path:
        return _CACHE['module']
    target = pathlib.Path(path)
    if not target.is_file():
        raise HTTPException(status_code=503, detail='adapter not found at WORLD_FACTS_ADAPTER')
    spec = importlib.util.spec_from_file_location('world_facts_adapter', target)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as error:  # noqa: BLE001 - report the reason, never guess
        _CACHE['error'] = '%s: %s' % (type(error).__name__, error)
        raise HTTPException(status_code=503, detail='adapter failed to load: %s' % _CACHE['error'])
    _CACHE.update(module=module, path=path, error=None)
    return module


def _database():
    path = os.environ.get('WORLD_SQLITE_PATH')
    if not path:
        raise HTTPException(status_code=503, detail='WORLD_SQLITE_PATH is not set')
    if not pathlib.Path(path).is_file():
        raise HTTPException(status_code=503, detail='world database not found')
    return path


@router.get('/{world_id}/{point_id}')
def point_facts(world_id: str, point_id: str):
    adapter = _adapter()
    database = _database()
    db = adapter.connect(database)
    try:
        names = adapter.labels(db, world_id)
        point = adapter.load_point(db, world_id, point_id)
        if point is None:
            raise HTTPException(status_code=404, detail='point not found')
        facts, gaps, unshown = adapter.adapt_point(
            db, world_id, point_id, names, os.environ.get('WORLD_FACTS_BACKEND', adapter.DEFAULT_BACKEND))
    finally:
        db.close()
    return {
        'worldId': world_id,
        'pointId': point_id,
        'sequence': point['sequence'],
        'previousPointId': point['previous_point_id'],
        'delta': adapter.json.loads(point['delta_json']) if point['delta_json'] else None,
        'facts': facts,
        'gaps': gaps,
        'notDisplayed': unshown,
    }
