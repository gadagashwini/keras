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
"""Gated Recurrent Unit layer."""
# pylint: disable=g-classes-have-attributes,g-direct-tensorflow-import

import uuid

from keras import activations
from keras import backend
from keras.engine import base_layer
from keras.layers.rnn import gru_lstm_utils
from keras.layers.rnn import gru_v1
from keras.layers.rnn.dropout_rnn_cell_mixin import DropoutRNNCellMixin
import tensorflow.compat.v2 as tf

from tensorflow.python.platform import tf_logging as logging
from tensorflow.python.util.tf_export import keras_export


@keras_export('keras.layers.GRUCell', v1=[])
class GRUCell(gru_v1.GRUCell):
  """Cell class for the GRU layer.

  See [the Keras RNN API guide](https://www.tensorflow.org/guide/keras/rnn)
  for details about the usage of RNN API.

  This class processes one step within the whole time sequence input, whereas
  `tf.keras.layer.GRU` processes the whole sequence.

  For example:

  >>> inputs = tf.random.normal([32, 10, 8])
  >>> rnn = tf.keras.layers.RNN(tf.keras.layers.GRUCell(4))
  >>> output = rnn(inputs)
  >>> print(output.shape)
  (32, 4)
  >>> rnn = tf.keras.layers.RNN(
  ...    tf.keras.layers.GRUCell(4),
  ...    return_sequences=True,
  ...    return_state=True)
  >>> whole_sequence_output, final_state = rnn(inputs)
  >>> print(whole_sequence_output.shape)
  (32, 10, 4)
  >>> print(final_state.shape)
  (32, 4)

  Args:
    units: Positive integer, dimensionality of the output space.
    activation: Activation function to use. Default: hyperbolic tangent
      (`tanh`). If you pass None, no activation is applied
      (ie. "linear" activation: `a(x) = x`).
    recurrent_activation: Activation function to use for the recurrent step.
      Default: sigmoid (`sigmoid`). If you pass `None`, no activation is
      applied (ie. "linear" activation: `a(x) = x`).
    use_bias: Boolean, (default `True`), whether the layer uses a bias vector.
    kernel_initializer: Initializer for the `kernel` weights matrix,
      used for the linear transformation of the inputs. Default:
      `glorot_uniform`.
    recurrent_initializer: Initializer for the `recurrent_kernel`
      weights matrix, used for the linear transformation of the recurrent state.
      Default: `orthogonal`.
    bias_initializer: Initializer for the bias vector. Default: `zeros`.
    kernel_regularizer: Regularizer function applied to the `kernel` weights
      matrix. Default: `None`.
    recurrent_regularizer: Regularizer function applied to the
      `recurrent_kernel` weights matrix. Default: `None`.
    bias_regularizer: Regularizer function applied to the bias vector. Default:
      `None`.
    kernel_constraint: Constraint function applied to the `kernel` weights
      matrix. Default: `None`.
    recurrent_constraint: Constraint function applied to the `recurrent_kernel`
      weights matrix. Default: `None`.
    bias_constraint: Constraint function applied to the bias vector. Default:
      `None`.
    dropout: Float between 0 and 1. Fraction of the units to drop for the
      linear transformation of the inputs. Default: 0.
    recurrent_dropout: Float between 0 and 1. Fraction of the units to drop for
      the linear transformation of the recurrent state. Default: 0.
    reset_after: GRU convention (whether to apply reset gate after or
      before matrix multiplication). False = "before",
      True = "after" (default and cuDNN compatible).

  Call arguments:
    inputs: A 2D tensor, with shape of `[batch, feature]`.
    states: A 2D tensor with shape of `[batch, units]`, which is the state from
      the previous time step. For timestep 0, the initial state provided by user
      will be feed to cell.
    training: Python boolean indicating whether the layer should behave in
      training mode or in inference mode. Only relevant when `dropout` or
      `recurrent_dropout` is used.
  """

  def __init__(self,
               units,
               activation='tanh',
               recurrent_activation='sigmoid',
               use_bias=True,
               kernel_initializer='glorot_uniform',
               recurrent_initializer='orthogonal',
               bias_initializer='zeros',
               kernel_regularizer=None,
               recurrent_regularizer=None,
               bias_regularizer=None,
               kernel_constraint=None,
               recurrent_constraint=None,
               bias_constraint=None,
               dropout=0.,
               recurrent_dropout=0.,
               reset_after=True,
               **kwargs):
    super(GRUCell, self).__init__(
        units,
        activation=activation,
        recurrent_activation=recurrent_activation,
        use_bias=use_bias,
        kernel_initializer=kernel_initializer,
        recurrent_initializer=recurrent_initializer,
        bias_initializer=bias_initializer,
        kernel_regularizer=kernel_regularizer,
        recurrent_regularizer=recurrent_regularizer,
        bias_regularizer=bias_regularizer,
        kernel_constraint=kernel_constraint,
        recurrent_constraint=recurrent_constraint,
        bias_constraint=bias_constraint,
        dropout=dropout,
        recurrent_dropout=recurrent_dropout,
        implementation=kwargs.pop('implementation', 2),
        reset_after=reset_after,
        **kwargs)


@keras_export('keras.layers.GRU', v1=[])
class GRU(DropoutRNNCellMixin, gru_v1.GRU, base_layer.BaseRandomLayer):
  """Gated Recurrent Unit - Cho et al. 2014.

  See [the Keras RNN API guide](https://www.tensorflow.org/guide/keras/rnn)
  for details about the usage of RNN API.

  Based on available runtime hardware and constraints, this layer
  will choose different implementations (cuDNN-based or pure-TensorFlow)
  to maximize the performance. If a GPU is available and all
  the arguments to the layer meet the requirement of the cuDNN kernel
  (see below for details), the layer will use a fast cuDNN implementation.

  The requirements to use the cuDNN implementation are:

  1. `activation` == `tanh`
  2. `recurrent_activation` == `sigmoid`
  3. `recurrent_dropout` == 0
  4. `unroll` is `False`
  5. `use_bias` is `True`
  6. `reset_after` is `True`
  7. Inputs, if use masking, are strictly right-padded.
  8. Eager execution is enabled in the outermost context.

  There are two variants of the GRU implementation. The default one is based on
  [v3](https://arxiv.org/abs/1406.1078v3) and has reset gate applied to hidden
  state before matrix multiplication. The other one is based on
  [original](https://arxiv.org/abs/1406.1078v1) and has the order reversed.

  The second variant is compatible with CuDNNGRU (GPU-only) and allows
  inference on CPU. Thus it has separate biases for `kernel` and
  `recurrent_kernel`. To use this variant, set `reset_after=True` and
  `recurrent_activation='sigmoid'`.

  For example:

  >>> inputs = tf.random.normal([32, 10, 8])
  >>> gru = tf.keras.layers.GRU(4)
  >>> output = gru(inputs)
  >>> print(output.shape)
  (32, 4)
  >>> gru = tf.keras.layers.GRU(4, return_sequences=True, return_state=True)
  >>> whole_sequence_output, final_state = gru(inputs)
  >>> print(whole_sequence_output.shape)
  (32, 10, 4)
  >>> print(final_state.shape)
  (32, 4)

  Args:
    units: Positive integer, dimensionality of the output space.
    activation: Activation function to use.
      Default: hyperbolic tangent (`tanh`).
      If you pass `None`, no activation is applied
      (ie. "linear" activation: `a(x) = x`).
    recurrent_activation: Activation function to use
      for the recurrent step.
      Default: sigmoid (`sigmoid`).
      If you pass `None`, no activation is applied
      (ie. "linear" activation: `a(x) = x`).
    use_bias: Boolean, (default `True`), whether the layer uses a bias vector.
    kernel_initializer: Initializer for the `kernel` weights matrix,
      used for the linear transformation of the inputs. Default:
      `glorot_uniform`.
    recurrent_initializer: Initializer for the `recurrent_kernel`
       weights matrix, used for the linear transformation of the recurrent
       state. Default: `orthogonal`.
    bias_initializer: Initializer for the bias vector. Default: `zeros`.
    kernel_regularizer: Regularizer function applied to the `kernel` weights
      matrix. Default: `None`.
    recurrent_regularizer: Regularizer function applied to the
      `recurrent_kernel` weights matrix. Default: `None`.
    bias_regularizer: Regularizer function applied to the bias vector. Default:
      `None`.
    activity_regularizer: Regularizer function applied to the output of the
      layer (its "activation"). Default: `None`.
    kernel_constraint: Constraint function applied to the `kernel` weights
      matrix. Default: `None`.
    recurrent_constraint: Constraint function applied to the `recurrent_kernel`
      weights matrix. Default: `None`.
    bias_constraint: Constraint function applied to the bias vector. Default:
      `None`.
    dropout: Float between 0 and 1. Fraction of the units to drop for the linear
      transformation of the inputs. Default: 0.
    recurrent_dropout: Float between 0 and 1. Fraction of the units to drop for
      the linear transformation of the recurrent state. Default: 0.
    return_sequences: Boolean. Whether to return the last output
      in the output sequence, or the full sequence. Default: `False`.
    return_state: Boolean. Whether to return the last state in addition to the
      output. Default: `False`.
    go_backwards: Boolean (default `False`).
      If True, process the input sequence backwards and return the
      reversed sequence.
    stateful: Boolean (default False). If True, the last state
      for each sample at index i in a batch will be used as initial
      state for the sample of index i in the following batch.
    unroll: Boolean (default False).
      If True, the network will be unrolled,
      else a symbolic loop will be used.
      Unrolling can speed-up a RNN,
      although it tends to be more memory-intensive.
      Unrolling is only suitable for short sequences.
    time_major: The shape format of the `inputs` and `outputs` tensors.
      If True, the inputs and outputs will be in shape
      `[timesteps, batch, feature]`, whereas in the False case, it will be
      `[batch, timesteps, feature]`. Using `time_major = True` is a bit more
      efficient because it avoids transposes at the beginning and end of the
      RNN calculation. However, most TensorFlow data is batch-major, so by
      default this function accepts input and emits output in batch-major
      form.
    reset_after: GRU convention (whether to apply reset gate after or
      before matrix multiplication). False = "before",
      True = "after" (default and cuDNN compatible).

  Call arguments:
    inputs: A 3D tensor, with shape `[batch, timesteps, feature]`.
    mask: Binary tensor of shape `[samples, timesteps]` indicating whether
      a given timestep should be masked  (optional, defaults to `None`).
      An individual `True` entry indicates that the corresponding timestep
      should be utilized, while a `False` entry indicates that the
      corresponding timestep should be ignored.
    training: Python boolean indicating whether the layer should behave in
      training mode or in inference mode. This argument is passed to the cell
      when calling it. This is only relevant if `dropout` or
      `recurrent_dropout` is used  (optional, defaults to `None`).
    initial_state: List of initial state tensors to be passed to the first
      call of the cell  (optional, defaults to `None` which causes creation
      of zero-filled initial state tensors).
  """

  def __init__(self,
               units,
               activation='tanh',
               recurrent_activation='sigmoid',
               use_bias=True,
               kernel_initializer='glorot_uniform',
               recurrent_initializer='orthogonal',
               bias_initializer='zeros',
               kernel_regularizer=None,
               recurrent_regularizer=None,
               bias_regularizer=None,
               activity_regularizer=None,
               kernel_constraint=None,
               recurrent_constraint=None,
               bias_constraint=None,
               dropout=0.,
               recurrent_dropout=0.,
               return_sequences=False,
               return_state=False,
               go_backwards=False,
               stateful=False,
               unroll=False,
               time_major=False,
               reset_after=True,
               **kwargs):
    # return_runtime is a flag for testing, which shows the real backend
    # implementation chosen by grappler in graph mode.
    self._return_runtime = kwargs.pop('return_runtime', False)

    super(GRU, self).__init__(
        units,
        activation=activation,
        recurrent_activation=recurrent_activation,
        use_bias=use_bias,
        kernel_initializer=kernel_initializer,
        recurrent_initializer=recurrent_initializer,
        bias_initializer=bias_initializer,
        kernel_regularizer=kernel_regularizer,
        recurrent_regularizer=recurrent_regularizer,
        bias_regularizer=bias_regularizer,
        activity_regularizer=activity_regularizer,
        kernel_constraint=kernel_constraint,
        recurrent_constraint=recurrent_constraint,
        bias_constraint=bias_constraint,
        dropout=dropout,
        recurrent_dropout=recurrent_dropout,
        implementation=kwargs.pop('implementation', 2),
        return_sequences=return_sequences,
        return_state=return_state,
        go_backwards=go_backwards,
        stateful=stateful,
        unroll=unroll,
        time_major=time_major,
        reset_after=reset_after,
        **kwargs)
    # GPU kernel uses following setting by default and not configurable.
    self._could_use_gpu_kernel = (
        self.activation in (activations.tanh, tf.tanh) and
        self.recurrent_activation in (activations.sigmoid, tf.sigmoid) and
        recurrent_dropout == 0 and not unroll and use_bias and
        reset_after and tf.compat.v1.executing_eagerly_outside_functions())
    if tf.config.list_logical_devices('GPU'):
      # Only show the message when there is GPU available, user will not care
      # about the cuDNN if there isn't any GPU.
      if self._could_use_gpu_kernel:
        logging.debug(gru_lstm_utils.CUDNN_AVAILABLE_MSG % self.name)
      else:
        logging.warning(gru_lstm_utils.CUDNN_NOT_AVAILABLE_MSG % self.name)

    if gru_lstm_utils.use_new_gru_lstm_impl():
      self._defun_wrapper = gru_lstm_utils.DefunWrapper(
          time_major, go_backwards, 'gru')

  def call(self, inputs, mask=None, training=None, initial_state=None):
    # The input should be dense, padded with zeros. If a ragged input is fed
    # into the layer, it is padded and the row lengths are used for masking.
    inputs, row_lengths = backend.convert_inputs_if_ragged(inputs)
    is_ragged_input = (row_lengths is not None)
    self._validate_args_if_ragged(is_ragged_input, mask)

    # GRU does not support constants. Ignore it during process.
    inputs, initial_state, _ = self._process_inputs(inputs, initial_state, None)

    if isinstance(mask, list):
      mask = mask[0]

    input_shape = backend.int_shape(inputs)
    timesteps = input_shape[0] if self.time_major else input_shape[1]

    if not self._could_use_gpu_kernel:
      kwargs = {'training': training}
      self._maybe_reset_cell_dropout_mask(self.cell)

      def step(cell_inputs, cell_states):
        return self.cell(cell_inputs, cell_states, **kwargs)

      last_output, outputs, states = backend.rnn(
          step,
          inputs,
          initial_state,
          constants=None,
          go_backwards=self.go_backwards,
          mask=mask,
          unroll=self.unroll,
          input_length=row_lengths if row_lengths is not None else timesteps,
          time_major=self.time_major,
          zero_output_for_mask=self.zero_output_for_mask)
      # This is a dummy tensor for testing purpose.
      runtime = gru_lstm_utils.runtime(gru_lstm_utils.RUNTIME_UNKNOWN)
    else:
      last_output, outputs, runtime, states = self._defun_gru_call(
          inputs, initial_state, training, mask, row_lengths)

    if self.stateful:
      updates = [tf.compat.v1.assign(self.states[0],
                                     tf.cast(states[0], self.states[0].dtype))]
      self.add_update(updates)

    if self.return_sequences:
      output = backend.maybe_convert_to_ragged(
          is_ragged_input, outputs, row_lengths, go_backwards=self.go_backwards)
    else:
      output = last_output

    if self.return_state:
      return [output] + list(states)
    elif self._return_runtime:
      return output, runtime
    else:
      return output

  def _defun_gru_call(self, inputs, initial_state, training, mask,
                      sequence_lengths):
    # Use the new defun approach for backend implementation swap.
    # Note that different implementations need to have same function
    # signature, eg, the tensor parameters need to have same shape and dtypes.

    self.reset_dropout_mask()
    dropout_mask = self.get_dropout_mask_for_cell(inputs, training, count=3)
    if dropout_mask is not None:
      inputs = inputs * dropout_mask[0]

    if gru_lstm_utils.use_new_gru_lstm_impl():
      gru_kwargs = {
          'inputs':
              inputs,
          'init_h':
              gru_lstm_utils.read_variable_value(initial_state[0]),
          'kernel':
              gru_lstm_utils.read_variable_value(self.cell.kernel),
          'recurrent_kernel':
              gru_lstm_utils.read_variable_value(self.cell.recurrent_kernel),
          'bias':
              gru_lstm_utils.read_variable_value(self.cell.bias),
          'mask':
              mask,
          'time_major':
              self.time_major,
          'go_backwards':
              self.go_backwards,
          'sequence_lengths':
              sequence_lengths,
          'zero_output_for_mask':
              self.zero_output_for_mask
      }
      (last_output, outputs, new_h,
       runtime) = self._defun_wrapper.defun_layer(**gru_kwargs)
    else:
      gpu_gru_kwargs = {
          'inputs':
              inputs,
          'init_h':
              gru_lstm_utils.read_variable_value(initial_state[0]),
          'kernel':
              gru_lstm_utils.read_variable_value(self.cell.kernel),
          'recurrent_kernel':
              gru_lstm_utils.read_variable_value(self.cell.recurrent_kernel),
          'bias':
              gru_lstm_utils.read_variable_value(self.cell.bias),
          'mask':
              mask,
          'time_major':
              self.time_major,
          'go_backwards':
              self.go_backwards,
          'sequence_lengths':
              sequence_lengths
      }
      normal_gru_kwargs = gpu_gru_kwargs.copy()
      normal_gru_kwargs.update({
          'zero_output_for_mask': self.zero_output_for_mask,
      })

      if tf.executing_eagerly():
        device_type = gru_lstm_utils.get_context_device_type()
        can_use_gpu = (
            # Either user specified GPU or unspecified but GPU is available.
            (device_type == gru_lstm_utils.GPU_DEVICE_NAME or
             (device_type is None and tf.config.list_logical_devices('GPU')))
            and
            (mask is None or
             gru_lstm_utils.is_cudnn_supported_inputs(mask, self.time_major)))
        # Under eager context, check the device placement and prefer the
        if can_use_gpu:
          last_output, outputs, new_h, runtime = gpu_gru(**gpu_gru_kwargs)
        else:
          last_output, outputs, new_h, runtime = standard_gru(
              **normal_gru_kwargs)
      else:
        last_output, outputs, new_h, runtime = gru_with_backend_selection(
            **normal_gru_kwargs)

    states = [new_h]
    return last_output, outputs, runtime, states


def standard_gru(inputs, init_h, kernel, recurrent_kernel, bias, mask,
                 time_major, go_backwards, sequence_lengths,
                 zero_output_for_mask):
  """GRU with standard kernel implementation.

  This implementation can be run on all types of hardware.

  This implementation lifts out all the layer weights and make them function
  parameters. It has same number of tensor input params as the cuDNN
  counterpart. The RNN step logic has been simplified, eg dropout and mask is
  removed since cuDNN implementation does not support that.

  Args:
    inputs: Input tensor of GRU layer.
    init_h: Initial state tensor for the cell output.
    kernel: Weights for cell kernel.
    recurrent_kernel: Weights for cell recurrent kernel.
    bias: Weights for cell kernel bias and recurrent bias. The bias contains the
      combined input_bias and recurrent_bias.
    mask: Binary tensor of shape `(samples, timesteps)` indicating whether
      a given timestep should be masked. An individual `True` entry indicates
      that the corresponding timestep should be utilized, while a `False` entry
      indicates that the corresponding timestep should be ignored.
    time_major: Boolean, whether the inputs are in the format of
      [time, batch, feature] or [batch, time, feature].
    go_backwards: Boolean (default False). If True, process the input sequence
      backwards and return the reversed sequence.
    sequence_lengths: The lengths of all sequences coming from a variable length
      input, such as ragged tensors. If the input has a fixed timestep size,
      this should be None.
    zero_output_for_mask: Boolean, whether to output zero for masked timestep.

  Returns:
    last_output: output tensor for the last timestep, which has shape
      [batch, units].
    outputs: output tensor for all timesteps, which has shape
      [batch, time, units].
    state_0: the cell output, which has same shape as init_h.
    runtime: constant string tensor which indicate real runtime hardware. This
      value is for testing purpose and should be used by user.
  """
  input_shape = backend.int_shape(inputs)
  timesteps = input_shape[0] if time_major else input_shape[1]

  input_bias, recurrent_bias = tf.unstack(bias)

  def step(cell_inputs, cell_states):
    """Step function that will be used by Keras RNN backend."""
    h_tm1 = cell_states[0]

    # inputs projected by all gate matrices at once
    matrix_x = backend.dot(cell_inputs, kernel)
    matrix_x = backend.bias_add(matrix_x, input_bias)

    x_z, x_r, x_h = tf.split(matrix_x, 3, axis=1)

    # hidden state projected by all gate matrices at once
    matrix_inner = backend.dot(h_tm1, recurrent_kernel)
    matrix_inner = backend.bias_add(matrix_inner, recurrent_bias)

    recurrent_z, recurrent_r, recurrent_h = tf.split(matrix_inner, 3, axis=1)
    z = tf.sigmoid(x_z + recurrent_z)
    r = tf.sigmoid(x_r + recurrent_r)
    hh = tf.tanh(x_h + r * recurrent_h)

    # previous and candidate state mixed by update gate
    h = z * h_tm1 + (1 - z) * hh
    return h, [h]

  last_output, outputs, new_states = backend.rnn(
      step,
      inputs, [init_h],
      constants=None,
      unroll=False,
      time_major=time_major,
      mask=mask,
      go_backwards=go_backwards,
      input_length=sequence_lengths
      if sequence_lengths is not None else timesteps,
      zero_output_for_mask=zero_output_for_mask)
  return last_output, outputs, new_states[0], gru_lstm_utils.runtime(
      gru_lstm_utils.RUNTIME_CPU)


def gpu_gru(inputs, init_h, kernel, recurrent_kernel, bias, mask, time_major,
            go_backwards, sequence_lengths):
  """GRU with cuDNN implementation which is only available for GPU."""
  if mask is not None:
    sequence_lengths = gru_lstm_utils.calculate_sequence_by_mask(
        mask, time_major)

  if not time_major and sequence_lengths is None:
    inputs = tf.transpose(inputs, perm=(1, 0, 2))
    seq_axis, batch_axis = (0, 1)
  else:
    seq_axis, batch_axis = (0, 1) if time_major else (1, 0)
  # For init_h, cuDNN expects one more dim of num_layers before or after batch
  # dim for time major or batch major inputs respectively
  init_h = tf.expand_dims(init_h, axis=seq_axis)

  weights = tf.split(kernel, 3, axis=1)
  weights += tf.split(recurrent_kernel, 3, axis=1)
  # Note that the bias was initialized as shape (2, 3 * units), flat it into
  # (6 * units)
  bias = tf.split(backend.flatten(bias), 6)

  if tf.sysconfig.get_build_info()['is_cuda_build']:
    # Note that the gate order for cuDNN is different from the canonical format.
    # canonical format is [z, r, h], whereas cuDNN is [r, z, h]. The swap need
    # to be done for kernel, recurrent_kernel, input_bias, recurrent_bias.
    # z is update gate weights.
    # r is reset gate weights.
    # h is output gate weights.
    weights[0], weights[1] = weights[1], weights[0]
    weights[3], weights[4] = weights[4], weights[3]
    bias[0], bias[1] = bias[1], bias[0]
    bias[3], bias[4] = bias[4], bias[3]

  params = gru_lstm_utils.canonical_to_params(
      weights=weights,
      biases=bias,
      shape=tf.constant([-1]),
      transpose_weights=True)

  if sequence_lengths is not None:
    if go_backwards:
      # Three reversals are required. E.g.,
      # normal input = [1, 2, 3, 0, 0]  # where 0 need to be masked
      # reversed_input_to_cudnn = [3, 2, 1, 0, 0]
      # output_from_cudnn = [6, 5, 4, 0, 0]
      # expected_output = [0, 0, 6, 5 ,4]
      inputs = tf.reverse_sequence(
          inputs, sequence_lengths, seq_axis=seq_axis, batch_axis=batch_axis)
    outputs, h, _, _, _ = tf.raw_ops.CudnnRNNV3(
        input=inputs,
        input_h=init_h,
        input_c=0,
        params=params,
        is_training=True,
        rnn_mode='gru',
        sequence_lengths=sequence_lengths,
        time_major=time_major)
    if go_backwards:
      outputs = tf.reverse_sequence(
          outputs, sequence_lengths, seq_axis=seq_axis, batch_axis=batch_axis)
      outputs = tf.reverse(outputs, axis=[seq_axis])
  else:
    if go_backwards:
      # Reverse axis 0 since the input is already convert to time major.
      inputs = tf.reverse(inputs, axis=[0])
    outputs, h, _, _ = tf.raw_ops.CudnnRNN(
        input=inputs, input_h=init_h, input_c=0, params=params,
        is_training=True, rnn_mode='gru')

  last_output = outputs[-1]
  if not time_major and sequence_lengths is None:
    outputs = tf.transpose(outputs, perm=[1, 0, 2])
  h = tf.squeeze(h, axis=seq_axis)

  # In the case of variable length input, the cudnn kernel will fill zeros for
  # the output, whereas the default keras behavior is to bring over the previous
  # output for t-1, so that in the return_sequence=False case, user can quickly
  # get the final effect output instead just 0s at the last timestep.
  # In order to mimic the default keras behavior, we copy the final h state as
  # the last_output, since it is numerically same as the output.
  if sequence_lengths is not None:
    last_output = h

  return last_output, outputs, h, gru_lstm_utils.runtime(
      gru_lstm_utils.RUNTIME_GPU)


def gru_with_backend_selection(inputs, init_h, kernel, recurrent_kernel, bias,
                               mask, time_major, go_backwards, sequence_lengths,
                               zero_output_for_mask):
  """Call the GRU with optimized backend kernel selection.

  Under the hood, this function will create two TF function, one with the most
  generic kernel and can run on all device condition, and the second one with
  cuDNN specific kernel, which can only run on GPU.

  The first function will be called with normal_lstm_params, while the second
  function is not called, but only registered in the graph. The Grappler will
  do the proper graph rewrite and swap the optimized TF function based on the
  device placement.

  Args:
    inputs: Input tensor of GRU layer.
    init_h: Initial state tensor for the cell output.
    kernel: Weights for cell kernel.
    recurrent_kernel: Weights for cell recurrent kernel.
    bias: Weights for cell kernel bias and recurrent bias. Only recurrent bias
      is used in this case.
    mask: Boolean tensor for mask out the steps within sequence.
      An individual `True` entry indicates that the corresponding timestep
      should be utilized, while a `False` entry indicates that the corresponding
      timestep should be ignored.
    time_major: Boolean, whether the inputs are in the format of
      [time, batch, feature] or [batch, time, feature].
    go_backwards: Boolean (default False). If True, process the input sequence
      backwards and return the reversed sequence.
    sequence_lengths: The lengths of all sequences coming from a variable length
      input, such as ragged tensors. If the input has a fixed timestep size,
      this should be None.
    zero_output_for_mask: Boolean, whether to output zero for masked timestep.

  Returns:
    List of output tensors, same as standard_gru.
  """
  params = {
      'inputs': inputs,
      'init_h': init_h,
      'kernel': kernel,
      'recurrent_kernel': recurrent_kernel,
      'bias': bias,
      'mask': mask,
      'time_major': time_major,
      'go_backwards': go_backwards,
      'sequence_lengths': sequence_lengths,
      'zero_output_for_mask': zero_output_for_mask,
  }

  def gpu_gru_with_fallback(inputs, init_h, kernel, recurrent_kernel, bias,
                            mask, time_major, go_backwards, sequence_lengths,
                            zero_output_for_mask):
    """Use cuDNN kernel when mask is none or strictly right padded."""
    if mask is None:
      return gpu_gru(
          inputs=inputs,
          init_h=init_h,
          kernel=kernel,
          recurrent_kernel=recurrent_kernel,
          bias=bias,
          mask=mask,
          time_major=time_major,
          go_backwards=go_backwards,
          sequence_lengths=sequence_lengths)

    def cudnn_gru_fn():
      return gpu_gru(
          inputs=inputs,
          init_h=init_h,
          kernel=kernel,
          recurrent_kernel=recurrent_kernel,
          bias=bias,
          mask=mask,
          time_major=time_major,
          go_backwards=go_backwards,
          sequence_lengths=sequence_lengths)

    def standard_gru_fn():
      return standard_gru(
          inputs=inputs,
          init_h=init_h,
          kernel=kernel,
          recurrent_kernel=recurrent_kernel,
          bias=bias,
          mask=mask,
          time_major=time_major,
          go_backwards=go_backwards,
          sequence_lengths=sequence_lengths,
          zero_output_for_mask=zero_output_for_mask)

    return tf.cond(
        gru_lstm_utils.is_cudnn_supported_inputs(mask, time_major),
        true_fn=cudnn_gru_fn,
        false_fn=standard_gru_fn)

  if gru_lstm_utils.use_new_gru_lstm_impl():
    # Chooses the implementation dynamically based on the running device.
    (last_output, outputs, new_h,
     runtime) = tf.__internal__.execute_fn_for_device(
         {
             gru_lstm_utils.CPU_DEVICE_NAME:
                 lambda: standard_gru(**params),
             gru_lstm_utils.GPU_DEVICE_NAME:
                 lambda: gpu_gru_with_fallback(**params)
         }, lambda: standard_gru(**params))
  else:
    # Each time a `tf.function` is called, we will give it a unique
    # identifiable API name, so that Grappler won't get confused when it
    # sees multiple GRU layers added into same graph, and it will be able
    # to pair up the different implementations across them.
    api_name = 'gru_' + str(uuid.uuid4())
    supportive_attribute = {
        'time_major': time_major,
        'go_backwards': go_backwards,
    }
    defun_standard_gru = gru_lstm_utils.generate_defun_backend(
        api_name, gru_lstm_utils.CPU_DEVICE_NAME, standard_gru,
        supportive_attribute)
    defun_gpu_gru = gru_lstm_utils.generate_defun_backend(
        api_name, gru_lstm_utils.GPU_DEVICE_NAME, gpu_gru_with_fallback,
        supportive_attribute)

    # Call the normal GRU impl and register the cuDNN impl function. The
    # grappler will kick in during session execution to optimize the graph.
    last_output, outputs, new_h, runtime = defun_standard_gru(**params)
    gru_lstm_utils.function_register(defun_gpu_gru, **params)

  return last_output, outputs, new_h, runtime
