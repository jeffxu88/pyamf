# Copyright (c) 2007-2009 The PyAMF Project.
# See LICENSE for details.

"""
SQLAlchemy adapter module.

@see: U{SQLAlchemy homepage (external)<http://www.sqlalchemy.org>}

@since: 0.4
"""

import sqlalchemy
from sqlalchemy.orm import collections

try:
    from sqlalchemy.orm import class_mapper, object_mapper
except ImportError:
    from sqlalchemy.orm.util import class_mapper, object_mapper

import pyamf
from pyamf.adapters import util

UnmappedInstanceError = None

try:
    class_mapper(dict)
except Exception, e:
    UnmappedInstanceError = e.__class__

class SaMappedClassAlias(pyamf.ClassAlias):
    KEY_ATTR = 'sa_key'
    LAZY_ATTR = 'sa_lazy'
    EXCLUDED_ATTRS = [
        '_sa_instance_state', '_sa_session_id', '_state',
        '_entity_name', '_instance_key', '_sa_class_manager',
        '_sa_adapter', '_sa_appender', '_sa_instrumented',
        '_sa_iterator', '_sa_remover', '_sa_initiator',
    ]

    def _getMapper(self, obj):
        """
        Returns sqlalchemy.orm.mapper.Mapper object.
        """
        if hasattr(self, 'primary_mapper'):
            return self.primary_mapper

        try:
            self.primary_mapper = object_mapper(obj)
        except UnmappedInstanceError:
            self.primary_mapper = None

        return self.primary_mapper

    def getAttrs(self, obj, *args, **kwargs):
        """
        Returns a C{tuple} containing 2 lists. The 1st is a list of allowed
        static attribute names, and the 2nd is a list of allowed dynamic
        attribute names.
        """
        mapper = self._getMapper(obj)

        if mapper is None:
            return pyamf.ClassAlias.getAttrs(self, obj, *args, **kwargs)

        if not hasattr(self, 'static_attrs'):
            self.static_attrs = [self.KEY_ATTR, self.LAZY_ATTR]

            for prop in mapper.iterate_properties:
                self.static_attrs.append(prop.key)

        dynamic_attrs = []

        for key in obj.__dict__.keys():
            if key in self.EXCLUDED_ATTRS:
                continue

            if key not in self.static_attrs:
                dynamic_attrs.append(key)

        return self.static_attrs, dynamic_attrs

    def getLazyAttrs(self, obj):
        """
        Returns a list of lazy attributes for this class
        """
        if hasattr(self, 'lazy_attrs'):
            return self.lazy_attrs

        self.lazy_attrs = []
        mapper = self._getMapper(obj)

        for prop in mapper.iterate_properties:
            if not hasattr(prop, 'lazy'):
                continue

            if prop.lazy:
                self.lazy_attrs.append(prop.key)

        return self.lazy_attrs

    def getAttributes(self, obj, *args, **kwargs):
        """
        Returns a C{tuple} containing a dict of static and dynamic attributes
        for C{obj}.
        """
        mapper = self._getMapper(obj)

        if mapper is None:
            return pyamf.ClassAlias.getAttributes(self, obj, *args, **kwargs)

        static_attrs = {}
        dynamic_attrs = {}

        static_attr_names, dynamic_attr_names = self.getAttrs(obj)

        for attr in static_attr_names:
             if attr in obj.__dict__:
                 static_attrs[attr] = getattr(obj, attr)

                 continue

             if attr in [self.KEY_ATTR, self.LAZY_ATTR]:
                 continue

             # attrs here are lazy but have not been loaded from the db yet ..
             static_attrs[attr] = pyamf.Undefined

        for attr in dynamic_attr_names:
            if attr in obj.__dict__:
                 dynamic_attrs[attr] = getattr(obj, attr)

        static_attrs[self.KEY_ATTR] = mapper.primary_key_from_instance(obj)
        static_attrs[self.LAZY_ATTR] = self.getLazyAttrs(obj)

        return static_attrs, dynamic_attrs

    def applyAttributes(self, obj, attrs, *args, **kwargs):
        """
        Add decoded attributes to instance.
        """
        mapper = self._getMapper(obj)

        if mapper is None:
            pyamf.ClassAlias.applyAttributes(self, obj, attrs, *args, **kwargs)

            return

        # Delete lazy-loaded attrs.
        # 
        # Doing it this way ensures that lazy-loaded attributes are not
        # attached to the object, even if there is a default value specified
        # in the __init__ method.
        #
        # This is the correct behavior, because SQLAlchemy ignores __init__.
        # So, an object retreived from a DB with SQLAlchemy will not have a
        # lazy-loaded value, even if __init__ specifies a default value.
        if self.LAZY_ATTR in attrs:
            obj_state = None

            if hasattr(sqlalchemy.orm.attributes, 'instance_state'):
                obj_state = sqlalchemy.orm.attributes.instance_state(obj)

            for lazy_attr in self.getLazyAttrs(obj):
                if lazy_attr in obj.__dict__:
                    # Delete directly from the dict, so
                    # SA callbacks are not triggered.
                    del obj.__dict__[lazy_attr]

                # Delete from committed_state so 
                # SA thinks this attribute was never modified.
                #
                # If the attribute was set in the __init__ method,
                # SA will think it is modified and will try to update
                # it in the database.
                if obj_state is not None:
                    if lazy_attr in obj_state.committed_state:
                        del obj_state.committed_state[lazy_attr]
                    if lazy_attr in obj_state.dict:
                        del obj_state.dict[lazy_attr]

                if lazy_attr in attrs:
                    del attrs[lazy_attr]

            del attrs[self.LAZY_ATTR]

        if self.KEY_ATTR in attrs:
            del attrs[self.KEY_ATTR]

        pyamf.util.set_attrs(obj, attrs)

def is_class_sa_mapped(klass):
    if not isinstance(klass, type):
        klass = type(klass)

    try:
        class_mapper(klass)
    except UnmappedInstanceError:
        return False

    return True

pyamf.register_alias_type(SaMappedClassAlias, is_class_sa_mapped)

pyamf.add_type(collections.InstrumentedList, util.to_list)
pyamf.add_type(collections.InstrumentedDict, util.to_dict)
pyamf.add_type(collections.InstrumentedSet, util.to_set)
