# Copyright 2022 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Library for map layout and corresponding tf.Variable."""

import collections
import contextlib
import re
import threading

from keras.dtensor import dtensor_api as dtensor
from keras.dtensor import lazy_variable
from keras.dtensor import utils
from keras.engine import base_layer

# pylint: disable=missing-class-docstring

# We will skip the path for certain attributes when mapping the layout, e.g.
# model._self_tracked_trackables, or layer._trainable_weights/
# _non_trainable_weights, etc. Those attributes are usually served as a cache,
# and the actual variable should be in somewhere else.
_KERAS_ATTRIBUTES_TO_SKIP = ['_self_tracked_trackables', '_trainable_weights',
                             '_non_trainable_weights']


_LAYOUT_MAP = threading.local()


def get_current_layout_map():
  return getattr(_LAYOUT_MAP, 'layout_map', None)


class LayoutMap(collections.MutableMapping):

  def __init__(self, mesh=None):
    """A dict like object that maps between string name and dtensor.Layout.

    Note that this class might behave differently than a normal dict, eg, it
    will treat the all the existing keys as a regex to map against input key.

    Args:
      mesh: An optional dtensor.Mesh that is used to provide all replicated
        layout as default when there isn't a layout is found based on the
        mapping.
    """
    self._layout_map = collections.OrderedDict()
    self._default_mesh = mesh

  def __getitem__(self, key):
    """Retrieve the corresponding layout by the string key.

    When there isn't an exact match, all the existing keys in the layout map
    will be treated as a regex and map against the input key again. The first
    match will be returned, based on the key insertion order. Return None if
    there isn't any match found.

    Args:
      key: the string key as the query for the layout.

    Returns:
      Corresponding layout based on the query.
    """
    if key in self._layout_map:
      return self._layout_map[key]

    for k in self._layout_map:
      if re.match(k, key):
        return self._layout_map[k]
    return None

  def __setitem__(self, key, layout):
    if key in self._layout_map:
      raise ValueError(f'{key} already exist in the LayoutMap with '
                       f'value {self._layout_map[key]}. Please make sure to '
                       'not use duplicated keys.')
    if not isinstance(layout, dtensor.Layout):
      raise ValueError(f'{layout} should be a dtensor.Layout type, '
                       'got {type(layout)}')

    self._layout_map[key] = layout

  def __delitem__(self, key):
    # let the dict to handle the key missing error
    return self._layout_map.pop(key)

  def __len__(self):
    return len(self._layout_map)

  def __iter__(self):
    return iter(self._layout_map)

  def get_default_mesh(self):
    return self._default_mesh


@contextlib.contextmanager
def layout_map_scope(layout_map):
  """Apply the layout to all the tf.Variables created under the scope.

  Create a scope that all the tf.Variable created under this scope
  will be lazily inited, and initialized later on with proper layout when the
  object path in the model is stable/finalized.

  Note that the layout mapping will use the object/attribute names as the key
  to map the variable against the layout.

  For subclassed models, the full object/attribute name is used as the key.
  For Functional/Sequential models, since the layers within the model do not get
  assigned to a meaningful attribute, we use `layer.name` as the key
  for the layer, followed by the attribute name. Keras ensures
  name uniqueness among the layers in all Functional/Sequential models.

  See the following examples that show the variable object names
  for different Keras model types:

  ```python
  layout_map = layout_map_lib.LayoutMap(mesh=self.mesh)
  layout_map['d1.kernel'] = layout_1
  layout_map['d1.bias'] = layout_2
  layout_map['d2.kernel'] = layout_3
  layout_map['d2.bias'] = layout_4

  ## Subclassed model
  class SubclassModel(tf.keras.Model):

    def __init__(self, name=None):
      super().__init__(name=name)
      self.d1 = tf.keras.layers.Dense(1000)
      self.d2 = tf.keras.layers.Dense(1000)

    def call(self, inputs):
      x = self.d1(inputs)
      return self.d2(x)

  with layout_map_scope(layout_map):
    model = SubclassModel()
  # Triggering the creation of weights within or outside of the scope works
  inputs = tf.zeros((10, 10))
  results = model(inputs)

  model.d1.kernel.layout == layout_1
  model.d1.bias.layout == layout_2
  model.d2.kernel.layout == layout_3
  model.d2.bias.layout == layout_4

  ## Functional model
  with layout_map_scope(layout_map):
    inputs = tf.keras.Input((10,), batch_size=10)
    x = tf.keras.layers.Dense(20, name='d1')(inputs)
    output = tf.keras.layers.Dense(30, name='d2')(x)

    model = tf.keras.Model(inputs, output)

  d1 = model.layers[1]
  d2 = model.layers[2]

  d1.kernel.layout == layout_1
  d1.bias.layout == layout_2
  d1.kernel.layout == layout_3
  d1.bias.layout == layout_4

  ## Sequential model
  with layout_map_scope(layout_map):
    model = tf.keras.Sequential([
        tf.keras.layers.Dense(20, name='d1', input_shape=(10,)),
        tf.keras.layers.Dense(30, name='d2')
    ])

  d1 = model.layers[0]
  d2 = model.layers[1]

  d1.kernel.layout == layout_1
  d1.bias.layout == layout_2
  d1.kernel.layout == layout_3
  d1.bias.layout == layout_4
  ```

  Args:
    layout_map: a LayoutMap which contains the variable_object_path (string) ->
      Layout. When a layout is not found for the variable, a default all
      replicated layout will be created for the variable.

  Yields:
    A context that will lazily initialize all `tf.Variable` objects
    within the model, with their attributed layouts.
  """
  previous_layout_map = get_current_layout_map()
  global _LAYOUT_MAP
  _LAYOUT_MAP.layout_map = layout_map

  with lazy_variable.lazy_init_scope():
    try:
      yield
    finally:
      _LAYOUT_MAP.layout_map = previous_layout_map


def _map_subclass_model_variable(model, layout_map):
  """Map/Replace LazyInitVariable for subclass model."""
  lazy_init_variable_to_tf_variable_map = {}

  # Note that the model._flatten is a method from tf.Module, and it returns
  # duplicated items (since some of the items have different paths).
  for path, variable in model._flatten(predicate=_is_lazy_init_variable,  # pylint: disable=protected-access
                                       with_path=True):
    # Note that path is a tuple that contains string and ints, eg:
    # ('d1', '_trainable_weights', 0) maps to model.d1._trainable_weights[0]
    if [a for a in _KERAS_ATTRIBUTES_TO_SKIP if a in path]:
      continue
    # Convert all the ints to string and join with .
    object_path = '.'.join([str(item) for item in path])

    new_variable = _create_dvariable(layout_map, object_path, variable)
    _set_object_by_path(model, path, new_variable)
    lazy_init_variable_to_tf_variable_map[id(variable)] = new_variable

  # After we replaced all the variables, we want to make sure all the cached
  # attributes are having the new variable, rather than old LazyInitVariable.
  for path, variable in model._flatten(predicate=_is_lazy_init_variable,  # pylint: disable=protected-access
                                       with_path=True):
    tf_variable = lazy_init_variable_to_tf_variable_map[id(variable)]
    _set_object_by_path(model, path, tf_variable)

  _init_state_variable_for_rng(model, layout_map)
  return model


def _map_functional_model_variable(model, layout_map):
  """Map/Replace LazyInitVariable for functional/sequential model."""
  lazy_init_variable_to_tf_variable_map = {}

  for layer in model.layers:
    # Note that layer name is unique among the functional/sequential model
    # when the layer name is not provided, Keras will auto generate a layer
    # name based on the class name.
    layer_name = layer.name
    for path, variable in layer._flatten(predicate=_is_lazy_init_variable,  # pylint: disable=protected-access
                                         with_path=True):
      # Note that path is a tuple that contains string and ints, eg:
      # ('d1', '_trainable_weights', 0) maps to model.d1._trainable_weights[0]
      if [a for a in _KERAS_ATTRIBUTES_TO_SKIP if a in path]:
        continue
      # Convert all the ints to string and join with .
      object_path = '.'.join([str(item) for item in path])
      # Also attach the layer name
      object_path = layer_name + '.' + object_path

      new_variable = _create_dvariable(layout_map, object_path, variable)
      _set_object_by_path(layer, path, new_variable)
      lazy_init_variable_to_tf_variable_map[id(variable)] = new_variable

    # After we replaced all the variables, we want to make sure all the cached
    # attributes are having the new variable, rather than old LazyInitVariable.
    for path, variable in layer._flatten(predicate=_is_lazy_init_variable,  # pylint: disable=protected-access
                                         with_path=True):
      tf_variable = lazy_init_variable_to_tf_variable_map[id(variable)]
      _set_object_by_path(layer, path, tf_variable)

  _init_state_variable_for_rng(model, layout_map)
  return model


def _init_state_variable_for_rng(model, layout_map):
  """Init the state variable in tf.ranodm.Generator.

  Since the BaseRandomLayer in keras explicitly untrack the tf.random.Generator,
  the variable in it will stay as LazyInitVariable, which cause runtime error if
  we don't replace them with proper DVariable. Since user usually are not
  aware the existance of those variable, we will just give them replicated
  layout since they are tiny.

  Args:
    model: the model whose layers will be checked to find the BaseRandomLayers.
    layout_map: used to get the default mesh information to create DVariable.
  """
  # pylint: disable=protected-access
  for l in model._flatten(
      predicate=lambda o: isinstance(o, base_layer.BaseRandomLayer)):
    keras_generator = l._random_generator
    if keras_generator._built and keras_generator._generator is None:
      raise ValueError(
          'Keras is expected to use tf.random.Generator when using DTensor API.'
          'Please call '
          '`tf.keras.backend.experimental.enable_tf_random_generator` at the '
          'beginning of your program.')
    if hasattr(keras_generator, '_generator') and _is_lazy_init_variable(
        keras_generator._generator._state_var):
      # Replace it with DVariable
      keras_generator._generator._state_var = _create_dvariable(
          layout_map, '', keras_generator._generator._state_var)
    else:
      # When the keras_generator is not built yet. Call the init function with
      # DTensor device to init all the variable with default replicated layout.
      with dtensor.run_on(layout_map.get_default_mesh()):
        keras_generator._maybe_init()


def _create_dvariable(layout_map, object_path, variable):
  """Create a new variable instead of using the LazyInitVariable.

  We choose to do this since even the LazyInitVariable might behavior like
  a normal tf.Variable/DVariable, it is not future proof for any new changes
  to variable class. It will also fail the instance type check in python,
  which could affect user's code when they do any filtering based on type to
  find any variables.

  Args:
    layout_map: a LayoutMap which contains the variable_object_path (string) ->
      Layout.
    object_path: string, the object attribute path for the variable.
    variable: LazyInitVariable which will be replaced by the newly created
      tf.Variable.
  Returns:
    A new tf.Variable with correct layout information.
  """
  # TODO(scottzhu): Revisit this in future and see if we can just reuse the
  # LazyInitVariable rather than creating a new tf.Variable instance.
  layout = layout_map[object_path]
  if layout is None:
    variable_rank = variable.shape.rank
    layout = dtensor.Layout.replicated(
        mesh=layout_map.get_default_mesh(),
        rank=variable_rank)
  init_val = variable._initial_value  # pylint: disable=protected-access
  if callable(init_val):
    with lazy_variable.disable_init_variable_creator():
      init_val = utils.call_with_layout(init_val, layout)
  else:
    # The init value is probably already created as a tensor, we will just copy
    # it to mesh and give it a proper layout.
    init_val = dtensor.copy_to_mesh(init_val, layout)
  new_variable = dtensor.DVariable(init_val,
                                   trainable=variable.trainable,
                                   name=variable.name)
  return new_variable


def _set_object_by_path(object_to_set, path, value):
  """Set the attribute of instance to the object.

  Args:
    object_to_set: the instance whose attribute should be set.
    path: the tuple/list of string and ints, representing the attribute names.
      Int means that the attribute to set is a item a list.
    value: the value of the attribute.
  """

  for i, attr_name in enumerate(path):
    if i == len(path) - 1:
      # We found the actual attribute to set
      if isinstance(attr_name, int):
      # This means we are trying to set an element in the array, make sure the
      # instance is array like object.
        object_to_set[attr_name] = value
      else:
        setattr(object_to_set, attr_name, value)
    else:
      if isinstance(attr_name, int):
        object_to_set = object_to_set[attr_name]
      else:
        object_to_set = getattr(object_to_set, attr_name)


def _is_lazy_init_variable(obj):
  return isinstance(obj, lazy_variable.LazyInitVariable)
