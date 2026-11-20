"""v2-only JSON Schema generation; frozen v1 exports remain untouched."""

from pydantic.json_schema import GenerateJsonSchema


class WireSchema(GenerateJsonSchema):
    def generate_definitions(self, inputs):
        mapping, definitions = super().generate_definitions(inputs)
        self._bounds(definitions)
        return mapping, definitions

    @classmethod
    def _bounds(cls, node):
        if isinstance(node, dict):
            # Nested validators can leave numeric constraints as metadata in
            # Pydantic's schema. JSON Schema consumers require these keywords.
            for old, new in (("ge", "minimum"), ("le", "maximum"),
                             ("gt", "exclusiveMinimum"), ("lt", "exclusiveMaximum")):
                if old in node:
                    bound = node.pop(old)
                    if new in node:
                        bound = (max if old in ("ge", "gt") else min)(bound, node[new])
                    node[new] = bound
            for value in node.values():
                cls._bounds(value)
        elif isinstance(node, list):
            for value in node:
                cls._bounds(value)
