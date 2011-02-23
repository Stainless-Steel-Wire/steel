import io
from .base import Field, DynamicValue, FullyDecoded


class SubStructure(Field):
    def __init__(self, structure, *args, **kwargs):
        self.structure = structure
        super(SubStructure, self).__init__(*args, **kwargs)

    def read(self, file):
        value = self.structure(file)

        value_bytes = b''
        # Force the evaluation of the entire structure in
        # order to make sure other fields work properly
        for field in self.structure._fields:
            getattr(value, field.name)
            value_bytes += value._raw_values[field.name]

        raise FullyDecoded(value_bytes, value)

    def encode(self, obj, value):
        output = io.BytesIO()
        value.save(output)
        return output.getvalue()


class List(Field):
    def __init__(self, field, *args, **kwargs):
        super(List, self).__init__(*args, **kwargs)
        self.field = field

    def read(self, file):
        value_bytes = b''
        values = []
        if self.instance:
            instance_field = field.for_instance(self.instance)

        for i in range(self.size):
            bytes, value = instance_field.read_value(file)
            value_bytes += bytes
            values.append(value)
        return values

    def encode(self, obj, values):
        encoded_values = []
        for value in values:
            encoded_values.append(self.field.encode(obj, value))
        return b''.join(encoded_values)


