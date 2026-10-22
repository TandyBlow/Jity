"""State construction and digest helpers over the authoritative WorldState."""
from app.schemas.world.canonical import canonical_digest
from app.schemas.world.contracts import (
    CharacterState, ItemState, LocationState, WorldInitialState, WorldState,
)


def build_initial_state(initial: WorldInitialState) -> WorldState:
    return WorldState(
        engineVersion=initial.engineVersion, schemaVersion=initial.schemaVersion,
        worldId=initial.worldId, protagonistId=initial.protagonistId,
        time=initial.initialTime.model_copy(), initial=initial.model_copy(),
        locations={key: LocationState(id=key) for key in initial.locations},
        items={key: ItemState(id=key, position=entity.initialPosition.model_copy())
               for key, entity in initial.items.items()},
        characters={
            key: CharacterState(
                id=key, position=entity.initialPosition.model_copy(),
                sanity=entity.initialSanity,
                tasks={task_id: task.model_copy() for task_id, task in entity.tasks.items()},
            )
            for key, entity in initial.characters.items()
        },
    )


def state_digest(state: WorldState) -> str:
    return canonical_digest(state.model_dump(mode='json'))
