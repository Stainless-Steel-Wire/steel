import copy

from biwako import common


class Trigger:
    def __init__(self):
        self.cache = {}

    def __get__(self, instance, owner):
        if owner is None:
            return self
        if instance not in self.cache:
            self.cache[instance] = BoundTrigger(instance)
        return self.cache[instance]


class BoundTrigger:
    def __init__(self, field):
        self.field = field
        self.functions = set()

    def __iter__(self):
        return iter(self.function)

    def __call__(self, func):
        # Used as a decorator
        self.functions.add(func)

    def apply(self, *args, **kwargs):
        # Called from within the appropriate code
        for func in self.functions:
            func(*args, **kwargs)


class Field(metaclass=common.DeclarativeFieldMetaclass):
    def __init__(self, label=None, *, size=None, offset=None, choices=(), **kwargs):
        self.name = ''
        self.label = label
        self.size = DynamicValue(size)
        if isinstance(size, Field):
            @self.after_encode
            def update_size(obj, value):
                setattr(obj, size.name, len(value))
        self.offset = offset
        # TODO: Actually support choices properly later
        self.choices = choices
        self.instance = None

    def for_instance(self, instance):
        field = copy.copy(self)
        for name, attr in self.__dict__.items():
            if isinstance(attr, DynamicValue):
                setattr(field, name, attr(instance))
        field.instance = instance
        return field

    def extract(self, obj):
        field = self.for_instance(obj)
        return field.decode(field.read(obj))

    def read(self, obj):
        # If the size can be determined easily, read
        # that number of bytes and return it directly.
        if self.size is not None:
            if self.size > 2 ** 10:
                print('%s is too big!' % self.name)
            return obj.read(self.size)

        # Otherwise, the field needs to supply its own
        # technique for determining how much data to read.
        raise NotImplementedError()

    def write(self, obj, value):
        # By default, this doesn't do much, but individual
        # fields can/should override it if necessary
        obj.write(value)

    def set_name(self, name):
        self.name = name
        label = self.label or name.replace('_', ' ')
        self.label = label.title()

    def attach_to_class(self, cls):
        cls._fields.append(self)

    def validate(self, obj, value):
        # This should raise a ValueError if the value is invalid
        # It should simply return without an error if it's valid
        field = self.for_instance(obj)

        # First, make sure the value can be encoded
        field.encode(value)

        # Then make sure it's a valid option, if applicable
        if self.choices and value not in set(v for v, desc in self.choices):
            raise ValueError("%r is not a valid choice" % value)

    def get_encoded_name(self):
        return '%s_encoded' % self.name

    after_encode = Trigger()
    after_decode = Trigger()

    def _extract(self, instance):
        field = self.for_instance(instance)
        try:
            return field.read(instance), None
        except FullyDecoded as obj:
            return obj.bytes, obj.value

    def read_value(self, file):
        try:
            bytes = self.read(file)
            value = self.decode(bytes)
            return bytes, value
        except FullyDecoded as obj:
            return obj.bytes, obj.value

    def __get__(self, instance, owner):
        if not instance:
            return self

        # Customizes the field for this particular instance
        # Use field instead of self for the rest of the method
        field = self.for_instance(instance)

        try:
            value = instance._extract(field)
        except IOError:
            raise AttributeError("Attribute %r has no data" % field.name)

        if field.name not in instance.__dict__:
            instance.__dict__[field.name] = field.decode(value)
            field.after_decode.apply(instance, value)
        return instance.__dict__[field.name]

    def __set__(self, instance, value):
        field = self.for_instance(instance)
        instance.__dict__[self.name] = value
        instance.__dict__[self.get_encoded_name()] = field.encode(value)
        self.after_encode.apply(instance, value)

    def __repr__(self):
        return '<%s: %s>' % (self.name, type(self).__name__)


class FullyDecoded(Exception):
    def __init__(self, bytes, value):
        self.bytes = bytes
        self.value = value


class DynamicValue:
    def __init__(self, value):
        self.value = value

    def __call__(self, obj):
        if isinstance(self.value, DynamicValue):
            return self.value(obj)
        elif isinstance(self.value, Field):
            return obj._get_value(self.value)
        elif hasattr(self.value, '__call__'):
            return self.value(obj)
        else:
            return self.value


# Special object used to instruct the reader to continue to the end of the file
def Remainder(obj):
    return -1


