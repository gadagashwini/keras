# Copyright 2019 The TensorFlow Authors. All Rights Reserved.
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
"""Keras image preprocessing layers."""

# pylint: disable=g-classes-have-attributes
# pylint: disable=g-direct-tensorflow-import

from keras import backend
from keras.engine import base_layer
from keras.engine import base_preprocessing_layer
from keras.layers.preprocessing import preprocessing_utils as utils
from keras.preprocessing.image import smart_resize
from keras.utils import tf_utils
import numpy as np
import tensorflow.compat.v2 as tf
from tensorflow.python.util.tf_export import keras_export
from tensorflow.tools.docs import doc_controls

ResizeMethod = tf.image.ResizeMethod

_RESIZE_METHODS = {
    'bilinear': ResizeMethod.BILINEAR,
    'nearest': ResizeMethod.NEAREST_NEIGHBOR,
    'bicubic': ResizeMethod.BICUBIC,
    'area': ResizeMethod.AREA,
    'lanczos3': ResizeMethod.LANCZOS3,
    'lanczos5': ResizeMethod.LANCZOS5,
    'gaussian': ResizeMethod.GAUSSIAN,
    'mitchellcubic': ResizeMethod.MITCHELLCUBIC
}

H_AXIS = -3
W_AXIS = -2


def check_fill_mode_and_interpolation(fill_mode, interpolation):
  if fill_mode not in {'reflect', 'wrap', 'constant', 'nearest'}:
    raise NotImplementedError(
        'Unknown `fill_mode` {}. Only `reflect`, `wrap`, '
        '`constant` and `nearest` are supported.'.format(fill_mode))
  if interpolation not in {'nearest', 'bilinear'}:
    raise NotImplementedError('Unknown `interpolation` {}. Only `nearest` and '
                              '`bilinear` are supported.'.format(interpolation))


@keras_export('keras.layers.Resizing',
              'keras.layers.experimental.preprocessing.Resizing')
class Resizing(base_layer.Layer):
  """A preprocessing layer which resizes images.

  This layer resizes an image input to a target height and width. The input
  should be a 4D (batched) or 3D (unbatched) tensor in `"channels_last"` format.
  Input pixel values can be of any range (e.g. `[0., 1.)` or `[0, 255]`) and of
  interger or floating point dtype. By default, the layer will output floats.

  This layer can be called on tf.RaggedTensor batches of input images of
  distinct sizes, and will resize the outputs to dense tensors of uniform size.

  For an overview and full list of preprocessing layers, see the preprocessing
  [guide](https://www.tensorflow.org/guide/keras/preprocessing_layers).

  Args:
    height: Integer, the height of the output shape.
    width: Integer, the width of the output shape.
    interpolation: String, the interpolation method. Defaults to `"bilinear"`.
      Supports `"bilinear"`, `"nearest"`, `"bicubic"`, `"area"`, `"lanczos3"`,
      `"lanczos5"`, `"gaussian"`, `"mitchellcubic"`.
    crop_to_aspect_ratio: If True, resize the images without aspect
      ratio distortion. When the original aspect ratio differs from the target
      aspect ratio, the output image will be cropped so as to return the largest
      possible window in the image (of size `(height, width)`) that matches
      the target aspect ratio. By default (`crop_to_aspect_ratio=False`),
      aspect ratio may not be preserved.
  """

  def __init__(self,
               height,
               width,
               interpolation='bilinear',
               crop_to_aspect_ratio=False,
               **kwargs):
    self.height = height
    self.width = width
    self.interpolation = interpolation
    self.crop_to_aspect_ratio = crop_to_aspect_ratio
    self._interpolation_method = get_interpolation(interpolation)
    super(Resizing, self).__init__(**kwargs)
    base_preprocessing_layer.keras_kpl_gauge.get_cell('Resizing').set(True)

  def call(self, inputs):
    # tf.image.resize will always output float32 and operate more efficiently on
    # float32 unless interpolation is nearest, in which case ouput type matches
    # input type.
    if self.interpolation == 'nearest':
      input_dtype = self.compute_dtype
    else:
      input_dtype = tf.float32
    inputs = utils.ensure_tensor(inputs, dtype=input_dtype)
    size = [self.height, self.width]
    if self.crop_to_aspect_ratio:
      def resize_to_aspect(x):
        if tf_utils.is_ragged(inputs):
          x = x.to_tensor()
        return smart_resize(
            x,
            size=size,
            interpolation=self._interpolation_method)

      if tf_utils.is_ragged(inputs):
        size_as_shape = tf.TensorShape(size)
        shape = size_as_shape + inputs.shape[-1:]
        spec = tf.TensorSpec(shape, input_dtype)
        outputs = tf.map_fn(resize_to_aspect, inputs, fn_output_signature=spec)
      else:
        outputs = resize_to_aspect(inputs)
    else:
      outputs = tf.image.resize(
          inputs,
          size=size,
          method=self._interpolation_method)
    return tf.cast(outputs, self.compute_dtype)

  def compute_output_shape(self, input_shape):
    input_shape = tf.TensorShape(input_shape).as_list()
    input_shape[H_AXIS] = self.height
    input_shape[W_AXIS] = self.width
    return tf.TensorShape(input_shape)

  def get_config(self):
    config = {
        'height': self.height,
        'width': self.width,
        'interpolation': self.interpolation,
        'crop_to_aspect_ratio': self.crop_to_aspect_ratio,
    }
    base_config = super(Resizing, self).get_config()
    return dict(list(base_config.items()) + list(config.items()))


@keras_export('keras.layers.CenterCrop',
              'keras.layers.experimental.preprocessing.CenterCrop')
class CenterCrop(base_layer.Layer):
  """A preprocessing layer which crops images.

  This layers crops the central portion of the images to a target size. If an
  image is smaller than the target size, it will be resized and cropped so as to
  return the largest possible window in the image that matches the target aspect
  ratio.

  Input pixel values can be of any range (e.g. `[0., 1.)` or `[0, 255]`) and
  of interger or floating point dtype. By default, the layer will output floats.

  For an overview and full list of preprocessing layers, see the preprocessing
  [guide](https://www.tensorflow.org/guide/keras/preprocessing_layers).

  Input shape:
    3D (unbatched) or 4D (batched) tensor with shape:
    `(..., height, width, channels)`, in `"channels_last"` format.

  Output shape:
    3D (unbatched) or 4D (batched) tensor with shape:
    `(..., target_height, target_width, channels)`.

  If the input height/width is even and the target height/width is odd (or
  inversely), the input image is left-padded by 1 pixel.

  Args:
    height: Integer, the height of the output shape.
    width: Integer, the width of the output shape.
  """

  def __init__(self, height, width, **kwargs):
    self.height = height
    self.width = width
    super(CenterCrop, self).__init__(**kwargs, autocast=False)
    base_preprocessing_layer.keras_kpl_gauge.get_cell('CenterCrop').set(True)

  def call(self, inputs):
    inputs = utils.ensure_tensor(inputs, self.compute_dtype)
    input_shape = tf.shape(inputs)
    h_diff = input_shape[H_AXIS] - self.height
    w_diff = input_shape[W_AXIS] - self.width

    def center_crop():
      h_start = tf.cast(h_diff / 2, tf.int32)
      w_start = tf.cast(w_diff / 2, tf.int32)
      return tf.image.crop_to_bounding_box(inputs, h_start, w_start,
                                           self.height, self.width)

    def upsize():
      outputs = smart_resize(inputs, [self.height, self.width])
      # smart_resize will always output float32, so we need to re-cast.
      return tf.cast(outputs, self.compute_dtype)

    return tf.cond(
        tf.reduce_all((h_diff >= 0, w_diff >= 0)), center_crop, upsize)

  def compute_output_shape(self, input_shape):
    input_shape = tf.TensorShape(input_shape).as_list()
    input_shape[H_AXIS] = self.height
    input_shape[W_AXIS] = self.width
    return tf.TensorShape(input_shape)

  def get_config(self):
    config = {
        'height': self.height,
        'width': self.width,
    }
    base_config = super(CenterCrop, self).get_config()
    return dict(list(base_config.items()) + list(config.items()))


@keras_export('keras.__internal__.layers.BaseImageAugmentationLayer')
class BaseImageAugmentationLayer(base_layer.BaseRandomLayer):
  """Abstract base layer for image augmentaion.

  This layer contains base functionalities for preprocessing layers which
  augment image related data, eg. image and in future, label and bounding boxes.
  The subclasses could avoid making certain mistakes and reduce code
  duplications.

  This layer requires you to implement one method: `augment_image()`, which
  augments one single image during the training. There are a few additional
  methods that you can implement for added functionality on the layer:

  `augment_label()`, which handles label augmentation if the layer supports
  that.

  `augment_bounding_box()`, which handles the bounding box augmentation, if the
  layer supports that.

  `get_random_tranformation()`, which should produce a random transformation
  setting. The tranformation object, which could be any type, will be passed to
  `augment_image`, `augment_label` and `augment_bounding_box`, to coodinate
  the randomness behavior, eg, in the RandomFlip layer, the image and
  bounding_box should be changed in the same way.

  The `call()` method support two formats of inputs:
  1. Single image tensor with 3D (HWC) or 4D (NHWC) format.
  2. A dict of tensors with stable keys. The supported keys are:
    `"images"`, `"labels"` and `"bounding_boxes"` at the moment. We might add
    more keys in future when we support more types of augmentation.

  The output of the `call()` will be in two formats, which will be the same
  structure as the inputs.

  The `call()` will handle the logic detecting the training/inference
  mode, unpack the inputs, forward to the correct function, and pack the output
  back to the same structure as the inputs.

  Example:

  ```python
  class RandomContrast(BaseAugmentationLayer):

    def __init__(self, factor=(0.5, 1.5), **kwargs):
      super().__init__(**kwargs)
      self._factor = factor

    def augment_image(self, image, transformation=None):
      random_factor = tf.random.uniform([], self._factor[0], self._factor[1])
      mean = tf.math.reduced_mean(inputs, axis=-1, keep_dim=True)
      output = (inputs - mean) * random_factor + mean
  ```

  Note that since the randomness is also a common functionnality, this layer
  also includes a tf.keras.backend.RandomGenerator, which can be used to produce
  the random numbers.  The random number generator is stored in the
  `self._random_generator` attribute.
  """

  def __init__(self, rate=1.0, seed=None, **kwargs):
    super().__init__(seed=seed, **kwargs)
    self.rate = rate

  @doc_controls.for_subclass_implementers
  def augment_image(self, image, transformation=None):
    """Augment a single image during training.

    Args:
      image: 3D image input tensor to the layer. Forwarded from `layer.call()`.
      transformation: The transformation object produced by
        `get_random_tranformation`. Used to coordinate the randomness between
        image, label and bounding box.

    Returns:
      output 3D tensor, which will be forward to `layer.call()`.
    """
    raise NotImplementedError()

  @doc_controls.for_subclass_implementers
  def augment_label(self, label, transformation=None):
    """Augment a single label during training.

    Args:
      label: 1D label to the layer. Forwarded from `layer.call()`.
      transformation: The transformation object produced by
        `get_random_tranformation`. Used to coordinate the randomness between
        image, label and bounding box.

    Returns:
      output 1D tensor, which will be forward to `layer.call()`.
    """
    raise NotImplementedError()

  @doc_controls.for_subclass_implementers
  def augment_bounding_box(self, bounding_box, transformation=None):
    """Augment bounding boxes for one image during training.

    Args:
      bounding_box: 2D bounding boxex to the layer. Forwarded from `call()`.
      transformation: The transformation object produced by
        `get_random_tranformation`. Used to coordinate the randomness between
        image, label and bounding box.

    Returns:
      output 2D tensor, which will be forward to `layer.call()`.
    """
    raise NotImplementedError()

  @doc_controls.for_subclass_implementers
  def get_random_tranformation(self):
    """Produce random transformation config.

    This is used to produce same randomness between image/label/bounding_box.

    Returns:
      Any type of object, which will be forwarded to `augment_image`,
      `augment_label` and `augment_bounding_box` as the `transformation`
      parameter.
    """
    return None

  def call(self, inputs, training=True):
    if training:
      inputs = self._format_inputs(inputs)
      images = inputs['images']
      if images.shape.rank == 3:
        return self._format_output(self._augment(inputs))
      elif images.shape.rank == 4:
        return self._format_output(self._batch_augment(inputs))
      else:
        raise ValueError('Image augmentation layers are expecting inputs to be '
                         'rank 3 (HWC) or 4D (NHWC) tensors. Got shape: '
                         f'{images.shape}')
    else:
      return inputs

  def _augment(self, inputs):
    transformation = self.get_random_tranformation()  # pylint: disable=assignment-from-none
    image = inputs.get('images', None)
    label = inputs.get('labels', None)
    bounding_box = inputs.get('bounding_boxes', None)

    image = utils.ensure_tensor(image, self.compute_dtype)
    image = self.augment_image(image, transformation=transformation)
    result = {'images': image}
    if label is not None:
      label = self.augment_label(label, transformation=transformation)
      result['labels'] = label
    if bounding_box is not None:
      bounding_box = self.augment_bounding_box(
          bounding_box, transformation=transformation)
      result['bounding_boxes'] = bounding_box
    return result

  def _batch_augment(self, inputs):
    return tf.map_fn(self._augment, inputs)

  def _format_inputs(self, inputs):
    if tf.is_tensor(inputs):
      # single image input tensor
      return {'images': inputs}
    elif isinstance(inputs, dict):
      # TODO(scottzhu): Check if it only contains the valid keys
      return inputs
    else:
      raise ValueError(
          f'Expect the inputs to be image tensor or dict. Got {inputs}')

  def _format_output(self, output):
    if isinstance(output, dict) and len(output) == 1:
      return output['images']
    else:
      return output


@keras_export('keras.layers.RandomCrop',
              'keras.layers.experimental.preprocessing.RandomCrop',
              v1=[])
class RandomCrop(base_layer.BaseRandomLayer):
  """A preprocessing layer which randomly crops images during training.

  During training, this layer will randomly choose a location to crop images
  down to a target size. The layer will crop all the images in the same batch to
  the same cropping location.

  At inference time, and during training if an input image is smaller than the
  target size, the input will be resized and cropped so as to return the largest
  possible window in the image that matches the target aspect ratio. If you need
  to apply random cropping at inference time, set `training` to True when
  calling the layer.

  Input pixel values can be of any range (e.g. `[0., 1.)` or `[0, 255]`) and
  of interger or floating point dtype. By default, the layer will output floats.

  For an overview and full list of preprocessing layers, see the preprocessing
  [guide](https://www.tensorflow.org/guide/keras/preprocessing_layers).

  Input shape:
    3D (unbatched) or 4D (batched) tensor with shape:
    `(..., height, width, channels)`, in `"channels_last"` format.

  Output shape:
    3D (unbatched) or 4D (batched) tensor with shape:
    `(..., target_height, target_width, channels)`.

  Args:
    height: Integer, the height of the output shape.
    width: Integer, the width of the output shape.
    seed: Integer. Used to create a random seed.
  """

  def __init__(self, height, width, seed=None, **kwargs):
    base_preprocessing_layer.keras_kpl_gauge.get_cell('RandomCrop').set(True)
    super(RandomCrop, self).__init__(**kwargs, autocast=False, seed=seed,
                                     force_generator=True)
    self.height = height
    self.width = width
    self.seed = seed

  def call(self, inputs, training=True):
    inputs = utils.ensure_tensor(inputs, dtype=self.compute_dtype)
    if training:
      input_shape = tf.shape(inputs)
      h_diff = input_shape[H_AXIS] - self.height
      w_diff = input_shape[W_AXIS] - self.width
      return tf.cond(
          tf.reduce_all((h_diff >= 0, w_diff >= 0)),
          lambda: self._random_crop(inputs),
          lambda: self._resize(inputs))
    else:
      return self._resize(inputs)

  def _random_crop(self, inputs):
    input_shape = tf.shape(inputs)
    h_diff = input_shape[H_AXIS] - self.height
    w_diff = input_shape[W_AXIS] - self.width
    dtype = input_shape.dtype
    rands = self._random_generator.random_uniform([2], 0, dtype.max, dtype)
    h_start = rands[0] % (h_diff + 1)
    w_start = rands[1] % (w_diff + 1)
    return tf.image.crop_to_bounding_box(inputs, h_start, w_start,
                                         self.height, self.width)

  def _resize(self, inputs):
    outputs = smart_resize(inputs, [self.height, self.width])
    # smart_resize will always output float32, so we need to re-cast.
    return tf.cast(outputs, self.compute_dtype)

  def compute_output_shape(self, input_shape):
    input_shape = tf.TensorShape(input_shape).as_list()
    input_shape[H_AXIS] = self.height
    input_shape[W_AXIS] = self.width
    return tf.TensorShape(input_shape)

  def get_config(self):
    config = {
        'height': self.height,
        'width': self.width,
        'seed': self.seed,
    }
    base_config = super(RandomCrop, self).get_config()
    return dict(list(base_config.items()) + list(config.items()))


@keras_export('keras.layers.Rescaling',
              'keras.layers.experimental.preprocessing.Rescaling')
class Rescaling(base_layer.Layer):
  """A preprocessing layer which rescales input values to a new range.

  This layer rescales every value of an input (often an image) by multiplying by
  `scale` and adding `offset`.

  For instance:

  1. To rescale an input in the ``[0, 255]`` range
  to be in the `[0, 1]` range, you would pass `scale=1./255`.

  2. To rescale an input in the ``[0, 255]`` range to be in the `[-1, 1]` range,
  you would pass `scale=1./127.5, offset=-1`.

  The rescaling is applied both during training and inference. Inputs can be
  of integer or floating point dtype, and by default the layer will output
  floats.

  For an overview and full list of preprocessing layers, see the preprocessing
  [guide](https://www.tensorflow.org/guide/keras/preprocessing_layers).

  Input shape:
    Arbitrary.

  Output shape:
    Same as input.

  Args:
    scale: Float, the scale to apply to the inputs.
    offset: Float, the offset to apply to the inputs.
  """

  def __init__(self, scale, offset=0., **kwargs):
    self.scale = scale
    self.offset = offset
    super(Rescaling, self).__init__(**kwargs)
    base_preprocessing_layer.keras_kpl_gauge.get_cell('Rescaling').set(True)

  def call(self, inputs):
    dtype = self.compute_dtype
    scale = tf.cast(self.scale, dtype)
    offset = tf.cast(self.offset, dtype)
    return tf.cast(inputs, dtype) * scale + offset

  def compute_output_shape(self, input_shape):
    return input_shape

  def get_config(self):
    config = {
        'scale': self.scale,
        'offset': self.offset,
    }
    base_config = super(Rescaling, self).get_config()
    return dict(list(base_config.items()) + list(config.items()))


HORIZONTAL = 'horizontal'
VERTICAL = 'vertical'
HORIZONTAL_AND_VERTICAL = 'horizontal_and_vertical'


@keras_export('keras.layers.RandomFlip',
              'keras.layers.experimental.preprocessing.RandomFlip',
              v1=[])
class RandomFlip(BaseImageAugmentationLayer):
  """A preprocessing layer which randomly flips images during training.

  This layer will flip the images horizontally and or vertically based on the
  `mode` attribute. During inference time, the output will be identical to
  input. Call the layer with `training=True` to flip the input.

  Input pixel values can be of any range (e.g. `[0., 1.)` or `[0, 255]`) and
  of interger or floating point dtype. By default, the layer will output floats.

  For an overview and full list of preprocessing layers, see the preprocessing
  [guide](https://www.tensorflow.org/guide/keras/preprocessing_layers).

  Input shape:
    3D (unbatched) or 4D (batched) tensor with shape:
    `(..., height, width, channels)`, in `"channels_last"` format.

  Output shape:
    3D (unbatched) or 4D (batched) tensor with shape:
    `(..., height, width, channels)`, in `"channels_last"` format.

  Arguments:
    mode: String indicating which flip mode to use. Can be `"horizontal"`,
      `"vertical"`, or `"horizontal_and_vertical"`. Defaults to
      `"horizontal_and_vertical"`. `"horizontal"` is a left-right flip and
      `"vertical"` is a top-bottom flip.
    seed: Integer. Used to create a random seed.
  """

  def __init__(self,
               mode=HORIZONTAL_AND_VERTICAL,
               seed=None,
               **kwargs):
    super(RandomFlip, self).__init__(seed=seed, force_generator=True, **kwargs)
    base_preprocessing_layer.keras_kpl_gauge.get_cell('RandomFlip').set(True)
    self.mode = mode
    if mode == HORIZONTAL:
      self.horizontal = True
      self.vertical = False
    elif mode == VERTICAL:
      self.horizontal = False
      self.vertical = True
    elif mode == HORIZONTAL_AND_VERTICAL:
      self.horizontal = True
      self.vertical = True
    else:
      raise ValueError('RandomFlip layer {name} received an unknown mode '
                       'argument {arg}'.format(name=self.name, arg=mode))
    self.seed = seed

  def augment_image(self, image, transformation=None):
    flipped_outputs = image
    if self.horizontal:
      seed = self._random_generator.make_seed_for_stateless_op()
      if seed is not None:
        flipped_outputs = tf.image.stateless_random_flip_left_right(
            flipped_outputs, seed=seed)
      else:
        flipped_outputs = tf.image.random_flip_left_right(
            flipped_outputs, self._random_generator.make_legacy_seed())
    if self.vertical:
      seed = self._random_generator.make_seed_for_stateless_op()
      if seed is not None:
        flipped_outputs = tf.image.stateless_random_flip_up_down(
            flipped_outputs, seed=seed)
      else:
        flipped_outputs = tf.image.random_flip_up_down(
            flipped_outputs, self._random_generator.make_legacy_seed())
    flipped_outputs.set_shape(image.shape)
    return flipped_outputs

  def compute_output_shape(self, input_shape):
    return input_shape

  def get_config(self):
    config = {
        'mode': self.mode,
        'seed': self.seed,
    }
    base_config = super(RandomFlip, self).get_config()
    return dict(list(base_config.items()) + list(config.items()))


# TODO(tanzheny): Add examples, here and everywhere.
@keras_export('keras.layers.RandomTranslation',
              'keras.layers.experimental.preprocessing.RandomTranslation',
              v1=[])
class RandomTranslation(BaseImageAugmentationLayer):
  """A preprocessing layer which randomly translates images during training.

  This layer will apply random translations to each image during training,
  filling empty space according to `fill_mode`.

  Input pixel values can be of any range (e.g. `[0., 1.)` or `[0, 255]`) and
  of interger or floating point dtype. By default, the layer will output floats.

  For an overview and full list of preprocessing layers, see the preprocessing
  [guide](https://www.tensorflow.org/guide/keras/preprocessing_layers).

  Args:
    height_factor: a float represented as fraction of value, or a tuple of size
      2 representing lower and upper bound for shifting vertically. A negative
      value means shifting image up, while a positive value means shifting image
      down. When represented as a single positive float, this value is used for
      both the upper and lower bound. For instance, `height_factor=(-0.2, 0.3)`
      results in an output shifted by a random amount in the range
      `[-20%, +30%]`.
      `height_factor=0.2` results in an output height shifted by a random amount
      in the range `[-20%, +20%]`.
    width_factor: a float represented as fraction of value, or a tuple of size 2
      representing lower and upper bound for shifting horizontally. A negative
      value means shifting image left, while a positive value means shifting
      image right. When represented as a single positive float, this value is
      used for both the upper and lower bound. For instance,
      `width_factor=(-0.2, 0.3)` results in an output shifted left by 20%, and
      shifted right by 30%. `width_factor=0.2` results in an output height
      shifted left or right by 20%.
    fill_mode: Points outside the boundaries of the input are filled according
      to the given mode (one of `{"constant", "reflect", "wrap", "nearest"}`).
      - *reflect*: `(d c b a | a b c d | d c b a)` The input is extended by
        reflecting about the edge of the last pixel.
      - *constant*: `(k k k k | a b c d | k k k k)` The input is extended by
        filling all values beyond the edge with the same constant value k = 0.
      - *wrap*: `(a b c d | a b c d | a b c d)` The input is extended by
        wrapping around to the opposite edge.
      - *nearest*: `(a a a a | a b c d | d d d d)` The input is extended by the
        nearest pixel.
    interpolation: Interpolation mode. Supported values: `"nearest"`,
      `"bilinear"`.
    seed: Integer. Used to create a random seed.
    fill_value: a float represents the value to be filled outside the boundaries
      when `fill_mode="constant"`.

  Input shape:
    3D (unbatched) or 4D (batched) tensor with shape:
    `(..., height, width, channels)`,  in `"channels_last"` format.

  Output shape:
    3D (unbatched) or 4D (batched) tensor with shape:
    `(..., height, width, channels)`,  in `"channels_last"` format.
  """

  def __init__(self,
               height_factor,
               width_factor,
               fill_mode='reflect',
               interpolation='bilinear',
               seed=None,
               fill_value=0.0,
               **kwargs):
    base_preprocessing_layer.keras_kpl_gauge.get_cell('RandomTranslation').set(
        True)
    super(RandomTranslation, self).__init__(seed=seed, force_generator=True,
                                            **kwargs)
    self.height_factor = height_factor
    if isinstance(height_factor, (tuple, list)):
      self.height_lower = height_factor[0]
      self.height_upper = height_factor[1]
    else:
      self.height_lower = -height_factor
      self.height_upper = height_factor
    if self.height_upper < self.height_lower:
      raise ValueError('`height_factor` cannot have upper bound less than '
                       'lower bound, got {}'.format(height_factor))
    if abs(self.height_lower) > 1. or abs(self.height_upper) > 1.:
      raise ValueError('`height_factor` must have values between [-1, 1], '
                       'got {}'.format(height_factor))

    self.width_factor = width_factor
    if isinstance(width_factor, (tuple, list)):
      self.width_lower = width_factor[0]
      self.width_upper = width_factor[1]
    else:
      self.width_lower = -width_factor
      self.width_upper = width_factor
    if self.width_upper < self.width_lower:
      raise ValueError('`width_factor` cannot have upper bound less than '
                       'lower bound, got {}'.format(width_factor))
    if abs(self.width_lower) > 1. or abs(self.width_upper) > 1.:
      raise ValueError('`width_factor` must have values between [-1, 1], '
                       'got {}'.format(width_factor))

    check_fill_mode_and_interpolation(fill_mode, interpolation)

    self.fill_mode = fill_mode
    self.fill_value = fill_value
    self.interpolation = interpolation
    self.seed = seed

  @tf.function
  def augment_image(self, image, transformation=None):
    """Translated inputs with random ops."""
    # The transform op only accepts rank 4 inputs, so if we have an unbatched
    # image, we need to temporarily expand dims to a batch.
    original_shape = image.shape
    inputs = tf.expand_dims(image, 0)

    inputs_shape = tf.shape(inputs)
    img_hd = tf.cast(inputs_shape[H_AXIS], tf.float32)
    img_wd = tf.cast(inputs_shape[W_AXIS], tf.float32)

    if transformation is None:
      transformation = self.get_random_tranformation()
    height_translation = transformation['height_translation']
    width_translation = transformation['width_translation']
    height_translation = height_translation * img_hd
    width_translation = width_translation * img_wd
    translations = tf.cast(
        tf.concat([width_translation, height_translation], axis=1),
        dtype=tf.float32)
    output = transform(
        inputs,
        get_translation_matrix(translations),
        interpolation=self.interpolation,
        fill_mode=self.fill_mode,
        fill_value=self.fill_value)

    output = tf.squeeze(output, 0)
    output.set_shape(original_shape)
    return output

  def get_random_tranformation(self):
    batch_size = 1
    height_translation = self._random_generator.random_uniform(
        shape=[batch_size, 1],
        minval=self.height_lower,
        maxval=self.height_upper,
        dtype=tf.float32)
    width_translation = self._random_generator.random_uniform(
        shape=[batch_size, 1],
        minval=self.width_lower,
        maxval=self.width_upper,
        dtype=tf.float32)
    return {'height_translation': height_translation,
            'width_translation': width_translation}

  def _batch_augment(self, inputs):
    # Change to vectorized_map for better performance, as well as work around
    # issue for different tensorspec between inputs and outputs.
    return tf.vectorized_map(self._augment, inputs)

  def compute_output_shape(self, input_shape):
    return input_shape

  def get_config(self):
    config = {
        'height_factor': self.height_factor,
        'width_factor': self.width_factor,
        'fill_mode': self.fill_mode,
        'fill_value': self.fill_value,
        'interpolation': self.interpolation,
        'seed': self.seed,
    }
    base_config = super(RandomTranslation, self).get_config()
    return dict(list(base_config.items()) + list(config.items()))


def get_translation_matrix(translations, name=None):
  """Returns projective transform(s) for the given translation(s).

  Args:
    translations: A matrix of 2-element lists representing `[dx, dy]`
      to translate for each image (for a batch of images).
    name: The name of the op.

  Returns:
    A tensor of shape `(num_images, 8)` projective transforms which can be given
      to `transform`.
  """
  with backend.name_scope(name or 'translation_matrix'):
    num_translations = tf.shape(translations)[0]
    # The translation matrix looks like:
    #     [[1 0 -dx]
    #      [0 1 -dy]
    #      [0 0 1]]
    # where the last entry is implicit.
    # Translation matrices are always float32.
    return tf.concat(
        values=[
            tf.ones((num_translations, 1), tf.float32),
            tf.zeros((num_translations, 1), tf.float32),
            -translations[:, 0, None],
            tf.zeros((num_translations, 1), tf.float32),
            tf.ones((num_translations, 1), tf.float32),
            -translations[:, 1, None],
            tf.zeros((num_translations, 2), tf.float32),
        ],
        axis=1)


def transform(images,
              transforms,
              fill_mode='reflect',
              fill_value=0.0,
              interpolation='bilinear',
              output_shape=None,
              name=None):
  """Applies the given transform(s) to the image(s).

  Args:
    images: A tensor of shape
      `(num_images, num_rows, num_columns, num_channels)` (NHWC). The rank must
      be statically known (the shape is not `TensorShape(None)`).
    transforms: Projective transform matrix/matrices. A vector of length 8 or
      tensor of size N x 8. If one row of transforms is [a0, a1, a2, b0, b1, b2,
      c0, c1], then it maps the *output* point `(x, y)` to a transformed *input*
      point `(x', y') = ((a0 x + a1 y + a2) / k, (b0 x + b1 y + b2) / k)`, where
      `k = c0 x + c1 y + 1`. The transforms are *inverted* compared to the
      transform mapping input points to output points. Note that gradients are
      not backpropagated into transformation parameters.
    fill_mode: Points outside the boundaries of the input are filled according
      to the given mode (one of `{"constant", "reflect", "wrap", "nearest"}`).
    fill_value: a float represents the value to be filled outside the boundaries
      when `fill_mode="constant"`.
    interpolation: Interpolation mode. Supported values: `"nearest"`,
      `"bilinear"`.
    output_shape: Output dimension after the transform, `[height, width]`.
      If `None`, output is the same size as input image.
    name: The name of the op.

  Fill mode behavior for each valid value is as follows:

  - reflect (d c b a | a b c d | d c b a)
  The input is extended by reflecting about the edge of the last pixel.

  - constant (k k k k | a b c d | k k k k)
  The input is extended by filling all
  values beyond the edge with the same constant value k = 0.

  - wrap (a b c d | a b c d | a b c d)
  The input is extended by wrapping around to the opposite edge.

  - nearest (a a a a | a b c d | d d d d)
  The input is extended by the nearest pixel.

  Input shape:
    4D tensor with shape: `(samples, height, width, channels)`,
      in `"channels_last"` format.

  Output shape:
    4D tensor with shape: `(samples, height, width, channels)`,
      in `"channels_last"` format.

  Returns:
    Image(s) with the same type and shape as `images`, with the given
    transform(s) applied. Transformed coordinates outside of the input image
    will be filled with zeros.

  Raises:
    TypeError: If `image` is an invalid type.
    ValueError: If output shape is not 1-D int32 Tensor.
  """
  with backend.name_scope(name or 'transform'):
    if output_shape is None:
      output_shape = tf.shape(images)[1:3]
      if not tf.executing_eagerly():
        output_shape_value = tf.get_static_value(output_shape)
        if output_shape_value is not None:
          output_shape = output_shape_value

    output_shape = tf.convert_to_tensor(
        output_shape, tf.int32, name='output_shape')

    if not output_shape.get_shape().is_compatible_with([2]):
      raise ValueError('output_shape must be a 1-D Tensor of 2 elements: '
                       'new_height, new_width, instead got '
                       '{}'.format(output_shape))

    fill_value = tf.convert_to_tensor(
        fill_value, tf.float32, name='fill_value')

    return tf.raw_ops.ImageProjectiveTransformV3(
        images=images,
        output_shape=output_shape,
        fill_value=fill_value,
        transforms=transforms,
        fill_mode=fill_mode.upper(),
        interpolation=interpolation.upper())


def get_rotation_matrix(angles, image_height, image_width, name=None):
  """Returns projective transform(s) for the given angle(s).

  Args:
    angles: A scalar angle to rotate all images by, or (for batches of images) a
      vector with an angle to rotate each image in the batch. The rank must be
      statically known (the shape is not `TensorShape(None)`).
    image_height: Height of the image(s) to be transformed.
    image_width: Width of the image(s) to be transformed.
    name: The name of the op.

  Returns:
    A tensor of shape (num_images, 8). Projective transforms which can be given
      to operation `image_projective_transform_v2`. If one row of transforms is
       [a0, a1, a2, b0, b1, b2, c0, c1], then it maps the *output* point
       `(x, y)` to a transformed *input* point
       `(x', y') = ((a0 x + a1 y + a2) / k, (b0 x + b1 y + b2) / k)`,
       where `k = c0 x + c1 y + 1`.
  """
  with backend.name_scope(name or 'rotation_matrix'):
    x_offset = ((image_width - 1) - (tf.cos(angles) *
                                     (image_width - 1) - tf.sin(angles) *
                                     (image_height - 1))) / 2.0
    y_offset = ((image_height - 1) - (tf.sin(angles) *
                                      (image_width - 1) + tf.cos(angles) *
                                      (image_height - 1))) / 2.0
    num_angles = tf.shape(angles)[0]
    return tf.concat(
        values=[
            tf.cos(angles)[:, None],
            -tf.sin(angles)[:, None],
            x_offset[:, None],
            tf.sin(angles)[:, None],
            tf.cos(angles)[:, None],
            y_offset[:, None],
            tf.zeros((num_angles, 2), tf.float32),
        ],
        axis=1)


@keras_export('keras.layers.RandomRotation',
              'keras.layers.experimental.preprocessing.RandomRotation',
              v1=[])
class RandomRotation(base_layer.BaseRandomLayer):
  """A preprocessing layer which randomly rotates images during training.

  This layer will apply random rotations to each image, filling empty space
  according to `fill_mode`.

  By default, random rotations are only applied during training.
  At inference time, the layer does nothing. If you need to apply random
  rotations at inference time, set `training` to True when calling the layer.

  Input pixel values can be of any range (e.g. `[0., 1.)` or `[0, 255]`) and
  of interger or floating point dtype. By default, the layer will output floats.

  For an overview and full list of preprocessing layers, see the preprocessing
  [guide](https://www.tensorflow.org/guide/keras/preprocessing_layers).

  Input shape:
    3D (unbatched) or 4D (batched) tensor with shape:
    `(..., height, width, channels)`, in `"channels_last"` format

  Output shape:
    3D (unbatched) or 4D (batched) tensor with shape:
    `(..., height, width, channels)`, in `"channels_last"` format

  Arguments:
    factor: a float represented as fraction of 2 Pi, or a tuple of size 2
      representing lower and upper bound for rotating clockwise and
      counter-clockwise. A positive values means rotating counter clock-wise,
      while a negative value means clock-wise. When represented as a single
      float, this value is used for both the upper and lower bound. For
      instance, `factor=(-0.2, 0.3)` results in an output rotation by a random
      amount in the range `[-20% * 2pi, 30% * 2pi]`. `factor=0.2` results in an
      output rotating by a random amount in the range `[-20% * 2pi, 20% * 2pi]`.
    fill_mode: Points outside the boundaries of the input are filled according
      to the given mode (one of `{"constant", "reflect", "wrap", "nearest"}`).
      - *reflect*: `(d c b a | a b c d | d c b a)` The input is extended by
        reflecting about the edge of the last pixel.
      - *constant*: `(k k k k | a b c d | k k k k)` The input is extended by
        filling all values beyond the edge with the same constant value k = 0.
      - *wrap*: `(a b c d | a b c d | a b c d)` The input is extended by
        wrapping around to the opposite edge.
      - *nearest*: `(a a a a | a b c d | d d d d)` The input is extended by the
        nearest pixel.
    interpolation: Interpolation mode. Supported values: `"nearest"`,
      `"bilinear"`.
    seed: Integer. Used to create a random seed.
    fill_value: a float represents the value to be filled outside the boundaries
      when `fill_mode="constant"`.
  """

  def __init__(self,
               factor,
               fill_mode='reflect',
               interpolation='bilinear',
               seed=None,
               fill_value=0.0,
               **kwargs):
    base_preprocessing_layer.keras_kpl_gauge.get_cell('RandomRotation').set(
        True)
    super(RandomRotation, self).__init__(seed=seed, force_generator=True,
                                         **kwargs)
    self.factor = factor
    if isinstance(factor, (tuple, list)):
      self.lower = factor[0]
      self.upper = factor[1]
    else:
      self.lower = -factor
      self.upper = factor
    if self.upper < self.lower:
      raise ValueError('Factor cannot have negative values, '
                       'got {}'.format(factor))
    check_fill_mode_and_interpolation(fill_mode, interpolation)
    self.fill_mode = fill_mode
    self.fill_value = fill_value
    self.interpolation = interpolation
    self.seed = seed

  def call(self, inputs, training=True):
    inputs = utils.ensure_tensor(inputs, self.compute_dtype)

    def random_rotated_inputs(inputs):
      """Rotated inputs with random ops."""
      original_shape = inputs.shape
      unbatched = inputs.shape.rank == 3
      # The transform op only accepts rank 4 inputs, so if we have an unbatched
      # image, we need to temporarily expand dims to a batch.
      if unbatched:
        inputs = tf.expand_dims(inputs, 0)
      inputs_shape = tf.shape(inputs)
      batch_size = inputs_shape[0]
      img_hd = tf.cast(inputs_shape[H_AXIS], tf.float32)
      img_wd = tf.cast(inputs_shape[W_AXIS], tf.float32)
      min_angle = self.lower * 2. * np.pi
      max_angle = self.upper * 2. * np.pi
      angles = self._random_generator.random_uniform(
          shape=[batch_size], minval=min_angle, maxval=max_angle)
      output = transform(
          inputs,
          get_rotation_matrix(angles, img_hd, img_wd),
          fill_mode=self.fill_mode,
          fill_value=self.fill_value,
          interpolation=self.interpolation)
      if unbatched:
        output = tf.squeeze(output, 0)
      output.set_shape(original_shape)
      return output

    if training:
      return random_rotated_inputs(inputs)
    else:
      return inputs

  def compute_output_shape(self, input_shape):
    return input_shape

  def get_config(self):
    config = {
        'factor': self.factor,
        'fill_mode': self.fill_mode,
        'fill_value': self.fill_value,
        'interpolation': self.interpolation,
        'seed': self.seed,
    }
    base_config = super(RandomRotation, self).get_config()
    return dict(list(base_config.items()) + list(config.items()))


@keras_export('keras.layers.RandomZoom',
              'keras.layers.experimental.preprocessing.RandomZoom',
              v1=[])
class RandomZoom(base_layer.BaseRandomLayer):
  """A preprocessing layer which randomly zooms images during training.

  This layer will randomly zoom in or out on each axis of an image
  independently, filling empty space according to `fill_mode`.

  Input pixel values can be of any range (e.g. `[0., 1.)` or `[0, 255]`) and
  of interger or floating point dtype. By default, the layer will output floats.

  For an overview and full list of preprocessing layers, see the preprocessing
  [guide](https://www.tensorflow.org/guide/keras/preprocessing_layers).

  Args:
    height_factor: a float represented as fraction of value, or a tuple of size
      2 representing lower and upper bound for zooming vertically. When
      represented as a single float, this value is used for both the upper and
      lower bound. A positive value means zooming out, while a negative value
      means zooming in. For instance, `height_factor=(0.2, 0.3)` result in an
      output zoomed out by a random amount in the range `[+20%, +30%]`.
      `height_factor=(-0.3, -0.2)` result in an output zoomed in by a random
      amount in the range `[+20%, +30%]`.
    width_factor: a float represented as fraction of value, or a tuple of size 2
      representing lower and upper bound for zooming horizontally. When
      represented as a single float, this value is used for both the upper and
      lower bound. For instance, `width_factor=(0.2, 0.3)` result in an output
      zooming out between 20% to 30%. `width_factor=(-0.3, -0.2)` result in an
      output zooming in between 20% to 30%. Defaults to `None`, i.e., zooming
      vertical and horizontal directions by preserving the aspect ratio.
    fill_mode: Points outside the boundaries of the input are filled according
      to the given mode (one of `{"constant", "reflect", "wrap", "nearest"}`).
      - *reflect*: `(d c b a | a b c d | d c b a)` The input is extended by
        reflecting about the edge of the last pixel.
      - *constant*: `(k k k k | a b c d | k k k k)` The input is extended by
        filling all values beyond the edge with the same constant value k = 0.
      - *wrap*: `(a b c d | a b c d | a b c d)` The input is extended by
        wrapping around to the opposite edge.
      - *nearest*: `(a a a a | a b c d | d d d d)` The input is extended by the
        nearest pixel.
    interpolation: Interpolation mode. Supported values: `"nearest"`,
      `"bilinear"`.
    seed: Integer. Used to create a random seed.
    fill_value: a float represents the value to be filled outside the boundaries
      when `fill_mode="constant"`.

  Example:

  >>> input_img = np.random.random((32, 224, 224, 3))
  >>> layer = tf.keras.layers.RandomZoom(.5, .2)
  >>> out_img = layer(input_img)
  >>> out_img.shape
  TensorShape([32, 224, 224, 3])

  Input shape:
    3D (unbatched) or 4D (batched) tensor with shape:
    `(..., height, width, channels)`, in `"channels_last"` format.

  Output shape:
    3D (unbatched) or 4D (batched) tensor with shape:
    `(..., height, width, channels)`, in `"channels_last"` format.
  """

  def __init__(self,
               height_factor,
               width_factor=None,
               fill_mode='reflect',
               interpolation='bilinear',
               seed=None,
               fill_value=0.0,
               **kwargs):
    base_preprocessing_layer.keras_kpl_gauge.get_cell('RandomZoom').set(True)
    super(RandomZoom, self).__init__(seed=seed, force_generator=True, **kwargs)
    self.height_factor = height_factor
    if isinstance(height_factor, (tuple, list)):
      self.height_lower = height_factor[0]
      self.height_upper = height_factor[1]
    else:
      self.height_lower = -height_factor
      self.height_upper = height_factor

    if abs(self.height_lower) > 1. or abs(self.height_upper) > 1.:
      raise ValueError('`height_factor` must have values between [-1, 1], '
                       'got {}'.format(height_factor))

    self.width_factor = width_factor
    if width_factor is not None:
      if isinstance(width_factor, (tuple, list)):
        self.width_lower = width_factor[0]
        self.width_upper = width_factor[1]
      else:
        self.width_lower = -width_factor  # pylint: disable=invalid-unary-operand-type
        self.width_upper = width_factor

      if self.width_lower < -1. or self.width_upper < -1.:
        raise ValueError('`width_factor` must have values larger than -1, '
                         'got {}'.format(width_factor))

    check_fill_mode_and_interpolation(fill_mode, interpolation)

    self.fill_mode = fill_mode
    self.fill_value = fill_value
    self.interpolation = interpolation
    self.seed = seed

  def call(self, inputs, training=True):
    inputs = utils.ensure_tensor(inputs, self.compute_dtype)

    def random_zoomed_inputs(inputs):
      """Zoomed inputs with random ops."""
      original_shape = inputs.shape
      unbatched = inputs.shape.rank == 3
      # The transform op only accepts rank 4 inputs, so if we have an unbatched
      # image, we need to temporarily expand dims to a batch.
      if unbatched:
        inputs = tf.expand_dims(inputs, 0)
      inputs_shape = tf.shape(inputs)
      batch_size = inputs_shape[0]
      img_hd = tf.cast(inputs_shape[H_AXIS], tf.float32)
      img_wd = tf.cast(inputs_shape[W_AXIS], tf.float32)
      height_zoom = self._random_generator.random_uniform(
          shape=[batch_size, 1],
          minval=1. + self.height_lower,
          maxval=1. + self.height_upper)
      if self.width_factor is not None:
        width_zoom = self._random_generator.random_uniform(
            shape=[batch_size, 1],
            minval=1. + self.width_lower,
            maxval=1. + self.width_upper)
      else:
        width_zoom = height_zoom
      zooms = tf.cast(
          tf.concat([width_zoom, height_zoom], axis=1),
          dtype=tf.float32)
      output = transform(
          inputs,
          get_zoom_matrix(zooms, img_hd, img_wd),
          fill_mode=self.fill_mode,
          fill_value=self.fill_value,
          interpolation=self.interpolation)
      if unbatched:
        output = tf.squeeze(output, 0)
      output.set_shape(original_shape)
      return output

    if training:
      return random_zoomed_inputs(inputs)
    else:
      return inputs

  def compute_output_shape(self, input_shape):
    return input_shape

  def get_config(self):
    config = {
        'height_factor': self.height_factor,
        'width_factor': self.width_factor,
        'fill_mode': self.fill_mode,
        'fill_value': self.fill_value,
        'interpolation': self.interpolation,
        'seed': self.seed,
    }
    base_config = super(RandomZoom, self).get_config()
    return dict(list(base_config.items()) + list(config.items()))


def get_zoom_matrix(zooms, image_height, image_width, name=None):
  """Returns projective transform(s) for the given zoom(s).

  Args:
    zooms: A matrix of 2-element lists representing `[zx, zy]` to zoom for each
      image (for a batch of images).
    image_height: Height of the image(s) to be transformed.
    image_width: Width of the image(s) to be transformed.
    name: The name of the op.

  Returns:
    A tensor of shape `(num_images, 8)`. Projective transforms which can be
      given to operation `image_projective_transform_v2`.
      If one row of transforms is
       `[a0, a1, a2, b0, b1, b2, c0, c1]`, then it maps the *output* point
       `(x, y)` to a transformed *input* point
       `(x', y') = ((a0 x + a1 y + a2) / k, (b0 x + b1 y + b2) / k)`,
       where `k = c0 x + c1 y + 1`.
  """
  with backend.name_scope(name or 'zoom_matrix'):
    num_zooms = tf.shape(zooms)[0]
    # The zoom matrix looks like:
    #     [[zx 0 0]
    #      [0 zy 0]
    #      [0 0 1]]
    # where the last entry is implicit.
    # Zoom matrices are always float32.
    x_offset = ((image_width - 1.) / 2.0) * (1.0 - zooms[:, 0, None])
    y_offset = ((image_height - 1.) / 2.0) * (1.0 - zooms[:, 1, None])
    return tf.concat(
        values=[
            zooms[:, 0, None],
            tf.zeros((num_zooms, 1), tf.float32),
            x_offset,
            tf.zeros((num_zooms, 1), tf.float32),
            zooms[:, 1, None],
            y_offset,
            tf.zeros((num_zooms, 2), tf.float32),
        ],
        axis=1)


@keras_export('keras.layers.RandomContrast',
              'keras.layers.experimental.preprocessing.RandomContrast',
              v1=[])
class RandomContrast(base_layer.BaseRandomLayer):
  """A preprocessing layer which randomly adjusts contrast during training.

  This layer will randomly adjust the contrast of an image or images by a random
  factor. Contrast is adjusted independently for each channel of each image
  during training.

  For each channel, this layer computes the mean of the image pixels in the
  channel and then adjusts each component `x` of each pixel to
  `(x - mean) * contrast_factor + mean`.

  Input pixel values can be of any range (e.g. `[0., 1.)` or `[0, 255]`) and
  in integer or floating point dtype. By default, the layer will output floats.
  The output value will be clipped to the range `[0, 255]`, the valid
  range of RGB colors.

  For an overview and full list of preprocessing layers, see the preprocessing
  [guide](https://www.tensorflow.org/guide/keras/preprocessing_layers).

  Input shape:
    3D (unbatched) or 4D (batched) tensor with shape:
    `(..., height, width, channels)`, in `"channels_last"` format.

  Output shape:
    3D (unbatched) or 4D (batched) tensor with shape:
    `(..., height, width, channels)`, in `"channels_last"` format.

  Arguments:
    factor: a positive float represented as fraction of value, or a tuple of
      size 2 representing lower and upper bound. When represented as a single
      float, lower = upper. The contrast factor will be randomly picked between
      `[1.0 - lower, 1.0 + upper]`. For any pixel x in the channel, the output
      will be `(x - mean) * factor + mean` where `mean` is the mean value of the
      channel.
    seed: Integer. Used to create a random seed.
  """

  def __init__(self, factor, seed=None, **kwargs):
    base_preprocessing_layer.keras_kpl_gauge.get_cell('RandomContrast').set(
        True)
    super(RandomContrast, self).__init__(seed=seed, force_generator=True,
                                         **kwargs)
    self.factor = factor
    if isinstance(factor, (tuple, list)):
      self.lower = factor[0]
      self.upper = factor[1]
    else:
      self.lower = self.upper = factor
    if self.lower < 0. or self.upper < 0. or self.lower > 1.:
      raise ValueError('Factor cannot have negative values or greater than 1.0,'
                       ' got {}'.format(factor))
    self.seed = seed

  def call(self, inputs, training=True):
    inputs = utils.ensure_tensor(inputs, self.compute_dtype)
    def random_contrasted_inputs(inputs):
      seed = self._random_generator.make_seed_for_stateless_op()
      if seed is not None:
        output = tf.image.stateless_random_contrast(
            inputs, 1. - self.lower, 1. + self.upper, seed=seed)
      else:
        output = tf.image.random_contrast(
            inputs, 1. - self.lower, 1. + self.upper,
            seed=self._random_generator.make_legacy_seed())
      output = tf.clip_by_value(output, 0, 255)
      output.set_shape(inputs.shape)
      return output

    if training:
      return random_contrasted_inputs(inputs)
    else:
      return inputs

  def compute_output_shape(self, input_shape):
    return input_shape

  def get_config(self):
    config = {
        'factor': self.factor,
        'seed': self.seed,
    }
    base_config = super(RandomContrast, self).get_config()
    return dict(list(base_config.items()) + list(config.items()))


@keras_export('keras.layers.RandomBrightness', v1=[])
class RandomBrightness(base_layer.BaseRandomLayer):
  """A preprocessing layer which randomly adjusts brightness during training.

  This layer will randomly increase/reduce the brightness for the input RGB
  images. At inference time, the output will be identical to the input.
  Call the layer with `training=True` to adjust the brightness of the input.

  Note that different brightness adjustment factors
  will be apply to each the images in the batch.

  For an overview and full list of preprocessing layers, see the preprocessing
  [guide](https://www.tensorflow.org/guide/keras/preprocessing_layers).

  Args:
    factor: Float or a list/tuple of 2 floats between -1.0 and 1.0. The
      factor is used to determine the lower bound and upper bound of the
      brightness adjustment. A float value will be chosen randomly between
      the limits. When -1.0 is chosen, the output image will be black, and
      when 1.0 is chosen, the image will be fully white. When only one float
      is provided, eg, 0.2, then -0.2 will be used for lower bound and 0.2
      will be used for upper bound.
    value_range: Optional list/tuple of 2 floats for the lower and upper limit
      of the values of the input data. Defaults to [0.0, 255.0]. Can be changed
      to e.g. [0.0, 1.0] if the image input has been scaled before this layer.
      The brightness adjustment will be scaled to this range, and the
      output values will be clipped to this range.
    seed: optional integer, for fixed RNG behavior.

  Inputs: 3D (HWC) or 4D (NHWC) tensor, with float or int dtype. Input pixel
    values can be of any range (e.g. `[0., 1.)` or `[0, 255]`)

  Output: 3D (HWC) or 4D (NHWC) tensor with brightness adjusted based on the
    `factor`. By default, the layer will output floats. The output value will
    be clipped to the range `[0, 255]`, the valid range of RGB colors, and
    rescaled based on the `value_range` if needed.

  Sample usage:

  ```python
  random_bright = tf.keras.layers.RandomBrightness(factor=0.2)

  # An image with shape [2, 2, 3]
  image = [[[1, 2, 3], [4 ,5 ,6]], [[7, 8, 9], [10, 11, 12]]]

  # Assume we randomly select the factor to be 0.1, then it will apply
  # 0.1 * 255 to all the channel
  output = random_bright(image, training=True)

  # output will be int64 with 25.5 added to each channel and round down.
  tf.Tensor([[[26.5, 27.5, 28.5]
              [29.5, 30.5, 31.5]]
             [[32.5, 33.5, 34.5]
              [35.5, 36.5, 37.5]]],
            shape=(2, 2, 3), dtype=int64)
  ```
  """
  _FACTOR_VALIDATION_ERROR = (
      'The `factor` argument should be a number (or a list of two numbers) '
      'in the range [-1.0, 1.0]. ')
  _VALUE_RANGE_VALIDATION_ERROR = (
      'The `value_range` argument should be a list of two numbers. ')

  def __init__(self, factor, value_range=(0, 255), seed=None, **kwargs):
    base_preprocessing_layer.keras_kpl_gauge.get_cell('RandomBrightness').set(
        True)
    super().__init__(seed=seed, force_generator=True, **kwargs)
    self._set_factor(factor)
    self._set_value_range(value_range)
    self._seed = seed

  def _set_value_range(self, value_range):
    if not isinstance(value_range, (tuple, list)):
      raise ValueError(
          self._VALUE_RANGE_VALIDATION_ERROR + f'Got {value_range}')
    if len(value_range) != 2:
      raise ValueError(
          self._VALUE_RANGE_VALIDATION_ERROR + f'Got {value_range}')
    self._value_range = sorted(value_range)

  def _set_factor(self, factor):
    if isinstance(factor, (tuple, list)):
      if len(factor) != 2:
        raise ValueError(self._FACTOR_VALIDATION_ERROR + f'Got {factor}')
      self._check_factor_range(factor[0])
      self._check_factor_range(factor[1])
      self._factor = sorted(factor)
    elif isinstance(factor, (int, float)):
      self._check_factor_range(factor)
      factor = abs(factor)
      self._factor = [-factor, factor]
    else:
      raise ValueError(self._FACTOR_VALIDATION_ERROR + f'Got {factor}')

  def _check_factor_range(self, input_number):
    if input_number > 1.0 or input_number < -1.0:
      raise ValueError(self._FACTOR_VALIDATION_ERROR + f'Got {input_number}')

  def call(self, inputs, training=True):
    if training:
      return self._brightness_adjust(inputs)
    else:
      return inputs

  def _brightness_adjust(self, images):
    images = utils.ensure_tensor(images, self.compute_dtype)
    rank = images.shape.rank
    if rank == 3:
      rgb_delta_shape = (1, 1, 1)
    elif rank == 4:
      # Keep only the batch dim. This will ensure to have same adjustment
      # with in one image, but different across the images.
      rgb_delta_shape = [tf.shape(images)[0], 1, 1, 1]
    else:
      raise ValueError(
          'Expected the input image to be rank 3 or 4. Got '
          f'inputs.shape = {images.shape}')
    rgb_delta = self._random_generator.random_uniform(
        shape=rgb_delta_shape,
        minval=self._factor[0],
        maxval=self._factor[1],
    )
    rgb_delta = rgb_delta * (self._value_range[1] - self._value_range[0])
    rgb_delta = tf.cast(rgb_delta, images.dtype)
    images += rgb_delta
    return tf.clip_by_value(
        images, self._value_range[0], self._value_range[1])

  def get_config(self):
    config = {
        'factor': self._factor,
        'value_range': self._value_range,
        'seed': self._seed,
    }
    base_config = super().get_config()
    return dict(list(base_config.items()) + list(config.items()))


@keras_export('keras.layers.RandomHeight',
              'keras.layers.experimental.preprocessing.RandomHeight',
              v1=[])
class RandomHeight(base_layer.BaseRandomLayer):
  """A preprocessing layer which randomly varies image height during training.

  This layer adjusts the height of a batch of images by a random factor.
  The input should be a 3D (unbatched) or 4D (batched) tensor in the
  `"channels_last"` image data format. Input pixel values can be of any range
  (e.g. `[0., 1.)` or `[0, 255]`) and of interger or floating point dtype. By
  default, the layer will output floats.


  By default, this layer is inactive during inference.

  For an overview and full list of preprocessing layers, see the preprocessing
  [guide](https://www.tensorflow.org/guide/keras/preprocessing_layers).

  Args:
    factor: A positive float (fraction of original height), or a tuple of size 2
      representing lower and upper bound for resizing vertically. When
      represented as a single float, this value is used for both the upper and
      lower bound. For instance, `factor=(0.2, 0.3)` results in an output with
      height changed by a random amount in the range `[20%, 30%]`.
      `factor=(-0.2, 0.3)` results in an output with height changed by a random
      amount in the range `[-20%, +30%]`. `factor=0.2` results in an output with
      height changed by a random amount in the range `[-20%, +20%]`.
    interpolation: String, the interpolation method. Defaults to `"bilinear"`.
      Supports `"bilinear"`, `"nearest"`, `"bicubic"`, `"area"`,
      `"lanczos3"`, `"lanczos5"`, `"gaussian"`, `"mitchellcubic"`.
    seed: Integer. Used to create a random seed.

  Input shape:
    3D (unbatched) or 4D (batched) tensor with shape:
    `(..., height, width, channels)`, in `"channels_last"` format.

  Output shape:
    3D (unbatched) or 4D (batched) tensor with shape:
    `(..., random_height, width, channels)`.
  """

  def __init__(self,
               factor,
               interpolation='bilinear',
               seed=None,
               **kwargs):
    base_preprocessing_layer.keras_kpl_gauge.get_cell('RandomHeight').set(True)
    super(RandomHeight, self).__init__(seed=seed, force_generator=True,
                                       **kwargs)
    self.factor = factor
    if isinstance(factor, (tuple, list)):
      self.height_lower = factor[0]
      self.height_upper = factor[1]
    else:
      self.height_lower = -factor
      self.height_upper = factor

    if self.height_upper < self.height_lower:
      raise ValueError('`factor` cannot have upper bound less than '
                       'lower bound, got {}'.format(factor))
    if self.height_lower < -1. or self.height_upper < -1.:
      raise ValueError('`factor` must have values larger than -1, '
                       'got {}'.format(factor))
    self.interpolation = interpolation
    self._interpolation_method = get_interpolation(interpolation)
    self.seed = seed

  def call(self, inputs, training=True):
    inputs = utils.ensure_tensor(inputs)

    def random_height_inputs(inputs):
      """Inputs height-adjusted with random ops."""
      inputs_shape = tf.shape(inputs)
      img_hd = tf.cast(inputs_shape[H_AXIS], tf.float32)
      img_wd = inputs_shape[W_AXIS]
      height_factor = self._random_generator.random_uniform(
          shape=[],
          minval=(1.0 + self.height_lower),
          maxval=(1.0 + self.height_upper))
      adjusted_height = tf.cast(height_factor * img_hd, tf.int32)
      adjusted_size = tf.stack([adjusted_height, img_wd])
      output = tf.image.resize(
          images=inputs, size=adjusted_size, method=self._interpolation_method)
      # tf.resize will output float32 in many cases regardless of input type.
      output = tf.cast(output, self.compute_dtype)
      output_shape = inputs.shape.as_list()
      output_shape[H_AXIS] = None
      output.set_shape(output_shape)
      return output

    if training:
      return random_height_inputs(inputs)
    else:
      return inputs

  def compute_output_shape(self, input_shape):
    input_shape = tf.TensorShape(input_shape).as_list()
    input_shape[H_AXIS] = None
    return tf.TensorShape(input_shape)

  def get_config(self):
    config = {
        'factor': self.factor,
        'interpolation': self.interpolation,
        'seed': self.seed,
    }
    base_config = super(RandomHeight, self).get_config()
    return dict(list(base_config.items()) + list(config.items()))


@keras_export('keras.layers.RandomWidth',
              'keras.layers.experimental.preprocessing.RandomWidth',
              v1=[])
class RandomWidth(base_layer.BaseRandomLayer):
  """A preprocessing layer which randomly varies image width during training.

  This layer will randomly adjusts the width of a batch of images of a
  batch of images by a random factor. The input should be a 3D (unbatched) or
  4D (batched) tensor in the `"channels_last"` image data format. Input pixel
  values can be of any range (e.g. `[0., 1.)` or `[0, 255]`) and of interger or
  floating point dtype. By default, the layer will output floats.

  By default, this layer is inactive during inference.

  For an overview and full list of preprocessing layers, see the preprocessing
  [guide](https://www.tensorflow.org/guide/keras/preprocessing_layers).

  Args:
    factor: A positive float (fraction of original width), or a tuple of size 2
      representing lower and upper bound for resizing vertically. When
      represented as a single float, this value is used for both the upper and
      lower bound. For instance, `factor=(0.2, 0.3)` results in an output with
      width changed by a random amount in the range `[20%, 30%]`. `factor=(-0.2,
      0.3)` results in an output with width changed by a random amount in the
      range `[-20%, +30%]`. `factor=0.2` results in an output with width changed
      by a random amount in the range `[-20%, +20%]`.
    interpolation: String, the interpolation method. Defaults to `bilinear`.
      Supports `"bilinear"`, `"nearest"`, `"bicubic"`, `"area"`, `"lanczos3"`,
      `"lanczos5"`, `"gaussian"`, `"mitchellcubic"`.
    seed: Integer. Used to create a random seed.

  Input shape:
    3D (unbatched) or 4D (batched) tensor with shape:
    `(..., height, width, channels)`, in `"channels_last"` format.

  Output shape:
    3D (unbatched) or 4D (batched) tensor with shape:
    `(..., height, random_width, channels)`.
  """

  def __init__(self,
               factor,
               interpolation='bilinear',
               seed=None,
               **kwargs):
    base_preprocessing_layer.keras_kpl_gauge.get_cell('RandomWidth').set(True)
    super(RandomWidth, self).__init__(seed=seed, force_generator=True, **kwargs)
    self.factor = factor
    if isinstance(factor, (tuple, list)):
      self.width_lower = factor[0]
      self.width_upper = factor[1]
    else:
      self.width_lower = -factor
      self.width_upper = factor
    if self.width_upper < self.width_lower:
      raise ValueError('`factor` cannot have upper bound less than '
                       'lower bound, got {}'.format(factor))
    if self.width_lower < -1. or self.width_upper < -1.:
      raise ValueError('`factor` must have values larger than -1, '
                       'got {}'.format(factor))
    self.interpolation = interpolation
    self._interpolation_method = get_interpolation(interpolation)
    self.seed = seed

  def call(self, inputs, training=True):
    inputs = utils.ensure_tensor(inputs)
    def random_width_inputs(inputs):
      """Inputs width-adjusted with random ops."""
      inputs_shape = tf.shape(inputs)
      img_hd = inputs_shape[H_AXIS]
      img_wd = tf.cast(inputs_shape[W_AXIS], tf.float32)
      width_factor = self._random_generator.random_uniform(
          shape=[],
          minval=(1.0 + self.width_lower),
          maxval=(1.0 + self.width_upper))
      adjusted_width = tf.cast(width_factor * img_wd, tf.int32)
      adjusted_size = tf.stack([img_hd, adjusted_width])
      output = tf.image.resize(
          images=inputs, size=adjusted_size, method=self._interpolation_method)
      # tf.resize will output float32 in many cases regardless of input type.
      output = tf.cast(output, self.compute_dtype)
      output_shape = inputs.shape.as_list()
      output_shape[W_AXIS] = None
      output.set_shape(output_shape)
      return output

    if training:
      return random_width_inputs(inputs)
    else:
      return inputs

  def compute_output_shape(self, input_shape):
    input_shape = tf.TensorShape(input_shape).as_list()
    input_shape[W_AXIS] = None
    return tf.TensorShape(input_shape)

  def get_config(self):
    config = {
        'factor': self.factor,
        'interpolation': self.interpolation,
        'seed': self.seed,
    }
    base_config = super(RandomWidth, self).get_config()
    return dict(list(base_config.items()) + list(config.items()))


def get_interpolation(interpolation):
  interpolation = interpolation.lower()
  if interpolation not in _RESIZE_METHODS:
    raise NotImplementedError(
        'Value not recognized for `interpolation`: {}. Supported values '
        'are: {}'.format(interpolation, _RESIZE_METHODS.keys()))
  return _RESIZE_METHODS[interpolation]
