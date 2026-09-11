class ScenarioGenerationError(RuntimeError):
    def __init__(self, message: str, model_output_id: int | None = None) -> None:
        super().__init__(message)
        self.model_output_id = model_output_id
