# Copyright 2018 The TensorFlow Authors. All Rights Reserved.
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
"""Tests for Adam."""

import tensorflow.compat.v2 as tf

from absl.testing import parameterized
import numpy as np
from keras.testing_infra import test_combinations
from keras.optimizers import optimizer_v1
from keras.optimizers.optimizer_v2 import adam
from keras.optimizers import learning_rate_schedule


def adam_update_numpy(param,
                      g_t,
                      t,
                      m,
                      v,
                      lr=0.001,
                      beta1=0.9,
                      beta2=0.999,
                      epsilon=1e-7):
  lr_t = lr * np.sqrt(1 - beta2**(t + 1)) / (1 - beta1**(t + 1))

  m_t = beta1 * m + (1 - beta1) * g_t
  v_t = beta2 * v + (1 - beta2) * g_t * g_t

  param_t = param - lr_t * m_t / (np.sqrt(v_t) + epsilon)
  return param_t, m_t, v_t


def adam_update_numpy_amsgrad(param,
                              g_t,
                              t,
                              m,
                              v,
                              vhat,
                              lr=0.001,
                              beta1=0.9,
                              beta2=0.999,
                              epsilon=1e-7):
  lr_t = lr * np.sqrt(1 - beta2**(t + 1)) / (1 - beta1**(t + 1))

  m_t = beta1 * m + (1 - beta1) * g_t
  v_t = beta2 * v + (1 - beta2) * g_t * g_t
  vhat_t = np.maximum(vhat, v_t)

  param_t = param - lr_t * m_t / (np.sqrt(vhat_t) + epsilon)
  return param_t, m_t, v_t, vhat_t


def adam_sparse_update_numpy_amsgrad(param,
                                     indices,
                                     g_t,
                                     t,
                                     m,
                                     v,
                                     vhat,
                                     lr=0.001,
                                     beta1=0.9,
                                     beta2=0.999,
                                     epsilon=1e-7):
  m_t, v_t, vhat_t, param_t = (np.copy(m), np.copy(v), np.copy(vhat),
                               np.copy(param))
  lr_t = lr * np.sqrt(1 - beta2**(t + 1)) / (1 - beta1**(t + 1))
  m_t_slice = beta1 * m[indices] + (1 - beta1) * g_t
  v_t_slice = beta2 * v[indices] + (1 - beta2) * g_t * g_t
  m_t[indices] = m_t_slice
  v_t[indices] = v_t_slice
  v_hat_t = np.maximum(vhat_t, v_t)
  v_hat_t_slice = v_hat_t[indices]
  param_t_slice = param[indices] - (
      lr_t * (m_t_slice / (np.sqrt(v_hat_t_slice) + epsilon)))
  param_t[indices] = param_t_slice
  return param_t, m_t, v_t, vhat_t


def get_beta_accumulators(opt, dtype):
  local_step = tf.cast(opt.iterations + 1, dtype)
  beta_1_t = tf.cast(opt._get_hyper("beta_1"), dtype)
  beta_1_power = tf.pow(beta_1_t, local_step)
  beta_2_t = tf.cast(opt._get_hyper("beta_2"), dtype)
  beta_2_power = tf.pow(beta_2_t, local_step)
  return (beta_1_power, beta_2_power)


class AdamOptimizerTest(tf.test.TestCase, parameterized.TestCase):

  def testSparse(self):
    # TODO(tanzheny, omalleyt): Fix test in eager mode.
    for dtype in [tf.half, tf.float32, tf.float64]:
      with tf.Graph().as_default(), self.cached_session():
        # Initialize variables for numpy implementation.
        m0, v0, m1, v1 = 0.0, 0.0, 0.0, 0.0
        var0_np = np.array([1.0, 1.0, 2.0], dtype=dtype.as_numpy_dtype)
        grads0_np = np.array([0.1, 0.0, 0.1], dtype=dtype.as_numpy_dtype)
        var1_np = np.array([3.0, 3.0, 4.0], dtype=dtype.as_numpy_dtype)
        grads1_np = np.array([0.01, 0.0, 0.01], dtype=dtype.as_numpy_dtype)

        var0 = tf.Variable(var0_np)
        var1 = tf.Variable(var1_np)
        grads0_np_indices = np.array([0, 2], dtype=np.int32)
        grads0 = tf.IndexedSlices(
            tf.constant(grads0_np[grads0_np_indices]),
            tf.constant(grads0_np_indices), tf.constant([3]))
        grads1_np_indices = np.array([0, 2], dtype=np.int32)
        grads1 = tf.IndexedSlices(
            tf.constant(grads1_np[grads1_np_indices]),
            tf.constant(grads1_np_indices), tf.constant([3]))
        opt = adam.Adam()
        update = opt.apply_gradients(zip([grads0, grads1], [var0, var1]))
        self.evaluate(tf.compat.v1.global_variables_initializer())

        # Fetch params to validate initial values
        self.assertAllClose([1.0, 1.0, 2.0], self.evaluate(var0))
        self.assertAllClose([3.0, 3.0, 4.0], self.evaluate(var1))

        beta_1_power, beta_2_power = get_beta_accumulators(opt, dtype)
        # Run 3 steps of Adam
        for t in range(3):
          self.assertAllCloseAccordingToType(0.9**(t + 1),
                                             self.evaluate(beta_1_power))
          self.assertAllCloseAccordingToType(0.999**(t + 1),
                                             self.evaluate(beta_2_power))
          update.run()

          var0_np, m0, v0 = adam_update_numpy(var0_np, grads0_np, t, m0, v0)
          var1_np, m1, v1 = adam_update_numpy(var1_np, grads1_np, t, m1, v1)

          # Validate updated params
          self.assertAllCloseAccordingToType(var0_np, self.evaluate(var0))
          self.assertAllCloseAccordingToType(var1_np, self.evaluate(var1))

  def testSparseDevicePlacement(self):
    # TODO(tanzheny, omalleyt): Fix test in eager mode.
    for index_dtype in [tf.int32, tf.int64]:
      with tf.Graph().as_default(), self.cached_session(
          force_gpu=tf.test.is_gpu_available()):
        # If a GPU is available, tests that all optimizer ops can be placed on
        # it (i.e. they have GPU kernels).
        var = tf.Variable([[1.0], [2.0]])
        indices = tf.constant([0, 1], dtype=index_dtype)
        g_sum = lambda: tf.reduce_sum(tf.gather(var, indices))  # pylint: disable=cell-var-from-loop
        optimizer = adam.Adam(3.0)
        minimize_op = optimizer.minimize(g_sum, var_list=[var])
        self.evaluate(tf.compat.v1.global_variables_initializer())
        minimize_op.run()

  def testSparseRepeatedIndices(self):
    # TODO(tanzheny, omalleyt): Fix test in eager mode.
    for dtype in [tf.half, tf.float32, tf.float64]:
      with tf.Graph().as_default(), self.cached_session():
        repeated_index_update_var = tf.Variable(
            [[1.0], [2.0]], dtype=dtype)
        aggregated_update_var = tf.Variable(
            [[1.0], [2.0]], dtype=dtype)
        grad_repeated_index = tf.IndexedSlices(
            tf.constant(
                [0.1, 0.1], shape=[2, 1], dtype=dtype),
            tf.constant([1, 1]),
            tf.constant([2, 1]))
        grad_aggregated = tf.IndexedSlices(
            tf.constant(
                [0.2], shape=[1, 1], dtype=dtype),
            tf.constant([1]),
            tf.constant([2, 1]))
        repeated_update = adam.Adam().apply_gradients(
            [(grad_repeated_index, repeated_index_update_var)])
        aggregated_update = adam.Adam().apply_gradients(
            [(grad_aggregated, aggregated_update_var)])
        self.evaluate(tf.compat.v1.global_variables_initializer())
        self.assertAllClose(aggregated_update_var,
                            self.evaluate(repeated_index_update_var))
        for _ in range(3):
          repeated_update.run()
          aggregated_update.run()
          self.assertAllClose(aggregated_update_var,
                              self.evaluate(repeated_index_update_var))

  def doTestBasic(self, use_callable_params=False):
    for i, dtype in enumerate([tf.half, tf.float32, tf.float64]):
      with self.cached_session():
        # Initialize variables for numpy implementation.
        m0, v0, m1, v1 = 0.0, 0.0, 0.0, 0.0
        var0_np = np.array([1.0, 2.0], dtype=dtype.as_numpy_dtype)
        grads0_np = np.array([0.1, 0.1], dtype=dtype.as_numpy_dtype)
        var1_np = np.array([3.0, 4.0], dtype=dtype.as_numpy_dtype)
        grads1_np = np.array([0.01, 0.01], dtype=dtype.as_numpy_dtype)

        var0 = tf.Variable(var0_np, name="var0_%d" % i)
        var1 = tf.Variable(var1_np, name="var1_%d" % i)
        grads0 = tf.constant(grads0_np)
        grads1 = tf.constant(grads1_np)

        learning_rate = lambda: 0.001
        beta1 = lambda: 0.9
        beta2 = lambda: 0.999
        epsilon = lambda: 1e-8
        if not use_callable_params:
          learning_rate = learning_rate()
          beta1 = beta1()
          beta2 = beta2()
          epsilon = epsilon()

        opt = adam.Adam(learning_rate=learning_rate)
        if not tf.executing_eagerly():
          update = opt.apply_gradients(zip([grads0, grads1], [var0, var1]))

        self.evaluate(tf.compat.v1.global_variables_initializer())
        # Run 3 steps of Adam
        for t in range(3):
          beta_1_power, beta_2_power = get_beta_accumulators(opt, dtype)
          self.assertAllCloseAccordingToType(0.9**(t + 1),
                                             self.evaluate(beta_1_power))
          self.assertAllCloseAccordingToType(0.999**(t + 1),
                                             self.evaluate(beta_2_power))
          if not tf.executing_eagerly():
            self.evaluate(update)
          else:
            opt.apply_gradients(zip([grads0, grads1], [var0, var1]))

          var0_np, m0, v0 = adam_update_numpy(var0_np, grads0_np, t, m0, v0)
          var1_np, m1, v1 = adam_update_numpy(var1_np, grads1_np, t, m1, v1)

          # Validate updated params
          self.assertAllCloseAccordingToType(var0_np, self.evaluate(var0))
          self.assertAllCloseAccordingToType(var1_np, self.evaluate(var1))

  @test_combinations.generate(
      test_combinations.combine(mode=["graph", "eager"]))
  def testResourceBasic(self):
    self.doTestBasic()

  @test_combinations.generate(test_combinations.combine(mode=["eager"]))
  def testBasicCallableParams(self):
    self.doTestBasic(use_callable_params=True)

  @test_combinations.generate(
      test_combinations.combine(mode=["graph", "eager"]))
  def testBasicWithAmsgrad(self):
    for i, dtype in enumerate([tf.half, tf.float32, tf.float64]):
      with self.cached_session():
        # Initialize variables for numpy implementation.
        m0, v0, v0hat, m1, v1, v1hat = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
        var0_np = np.array([1.0, 2.0], dtype=dtype.as_numpy_dtype)
        grads0_np = np.array([0.1, 0.1], dtype=dtype.as_numpy_dtype)
        var1_np = np.array([3.0, 4.0], dtype=dtype.as_numpy_dtype)
        grads1_np = np.array([0.01, 0.01], dtype=dtype.as_numpy_dtype)

        var0 = tf.Variable(var0_np, name="var0_%d" % i)
        var1 = tf.Variable(var1_np, name="var1_%d" % i)
        grads0 = tf.constant(grads0_np)
        grads1 = tf.constant(grads1_np)

        opt = adam.Adam(amsgrad=True)
        if not tf.executing_eagerly():
          update = opt.apply_gradients(zip([grads0, grads1], [var0, var1]))

        self.evaluate(tf.compat.v1.global_variables_initializer())
        # Run 3 steps of Adam
        for t in range(3):
          beta_1_power, beta_2_power = get_beta_accumulators(opt, dtype)
          self.assertAllCloseAccordingToType(0.9**(t + 1),
                                             self.evaluate(beta_1_power))
          self.assertAllCloseAccordingToType(0.999**(t + 1),
                                             self.evaluate(beta_2_power))
          if not tf.executing_eagerly():
            self.evaluate(update)
          else:
            opt.apply_gradients(zip([grads0, grads1], [var0, var1]))

          var0_np, m0, v0, v0hat = adam_update_numpy_amsgrad(
              var0_np, grads0_np, t, m0, v0, v0hat)
          var1_np, m1, v1, v1hat = adam_update_numpy_amsgrad(
              var1_np, grads1_np, t, m1, v1, v1hat)

          # Validate updated params
          self.assertAllCloseAccordingToType(var0_np, self.evaluate(var0))
          self.assertAllCloseAccordingToType(var1_np, self.evaluate(var1))

  @test_combinations.generate(
      test_combinations.combine(mode=["graph", "eager"]))
  def testSparseWithAmsgrad(self):
    # dtypes.half does not work on gpu + eager.
    for dtype in [tf.float32, tf.float64]:
      with self.cached_session():
        m0 = np.array([[0.0], [0.0]])
        v0 = np.array([[0.0], [0.0]])
        v0hat = np.array([[0.0], [0.0]])
        indices_np = np.array([1])
        indices = tf.constant(indices_np, dtype=tf.int32)
        var0_np = np.array([[1.0], [2.0]], dtype=dtype.as_numpy_dtype)
        repeated_index_update_var = tf.Variable(var0_np, dtype=dtype)
        aggregated_update_var = tf.Variable(var0_np, dtype=dtype)
        grads0_np = np.array([[0.2]], dtype=dtype.as_numpy_dtype)
        grad_repeated_index = tf.IndexedSlices(
            tf.constant([0.1, 0.1], shape=[2, 1], dtype=dtype),
            tf.constant([1, 1]), tf.constant([2, 1]))
        grad_aggregated = tf.IndexedSlices(grads0_np, indices,
                                            tf.constant([2, 1]))
        opt_repeated = adam.Adam(amsgrad=True)
        opt_aggregated = adam.Adam(amsgrad=True)
        if not tf.executing_eagerly():
          repeated_update = opt_repeated.apply_gradients(
              [(grad_repeated_index, repeated_index_update_var)])
          aggregated_update = opt_aggregated.apply_gradients(
              [(grad_aggregated, aggregated_update_var)])
        self.evaluate(tf.compat.v1.global_variables_initializer())
        self.assertAllClose(
            self.evaluate(aggregated_update_var),
            self.evaluate(repeated_index_update_var))
        for t in range(3):
          if not tf.executing_eagerly():
            self.evaluate(repeated_update)
            self.evaluate(aggregated_update)
          else:
            opt_repeated.apply_gradients(
                [(grad_repeated_index, repeated_index_update_var)])
            opt_aggregated.apply_gradients(
                [(grad_aggregated, aggregated_update_var)])

          var0_np, m0, v0, v0hat = adam_sparse_update_numpy_amsgrad(
              var0_np, indices_np, grads0_np, t, m0, v0, v0hat)

          # Validate updated params
          self.assertAllCloseAccordingToType(
              var0_np, self.evaluate(aggregated_update_var))
          self.assertAllCloseAccordingToType(
              self.evaluate(aggregated_update_var),
              self.evaluate(repeated_index_update_var))

  def testBasicWithLearningRateDecay(self):
    # TODO(tanzheny, omalleyt): Fix test in eager mode.
    for i, dtype in enumerate([tf.half, tf.float32, tf.float64]):
      with tf.Graph().as_default(), self.cached_session():
        # Initialize variables for numpy implementation.
        m0, v0, m1, v1 = 0.0, 0.0, 0.0, 0.0
        var0_np = np.array([1.0, 2.0], dtype=dtype.as_numpy_dtype)
        grads0_np = np.array([0.1, 0.1], dtype=dtype.as_numpy_dtype)
        var1_np = np.array([3.0, 4.0], dtype=dtype.as_numpy_dtype)
        grads1_np = np.array([0.01, 0.01], dtype=dtype.as_numpy_dtype)

        var0 = tf.Variable(var0_np, name="var0_%d" % i)
        var1 = tf.Variable(var1_np, name="var1_%d" % i)
        grads0 = tf.constant(grads0_np)
        grads1 = tf.constant(grads1_np)

        learning_rate = 0.001
        beta_1 = 0.9
        beta_2 = 0.999
        epsilon = 1e-7
        decay = 0.5

        opt = adam.Adam(
            learning_rate=learning_rate,
            beta_1=beta_1,
            beta_2=beta_2,
            epsilon=epsilon,
            decay=decay)
        update = opt.apply_gradients(zip([grads0, grads1], [var0, var1]))

        self.evaluate(tf.compat.v1.global_variables_initializer())
        # Run 3 steps of Adam
        for t in range(3):
          self.evaluate(update)
          lr_np = learning_rate / (1 + decay * t)

          var0_np, m0, v0 = adam_update_numpy(
              var0_np, grads0_np, t, m0, v0, lr=lr_np)
          var1_np, m1, v1 = adam_update_numpy(
              var1_np, grads1_np, t, m1, v1, lr=lr_np)

          # Validate updated params
          self.assertAllCloseAccordingToType(var0_np, self.evaluate(var0))
          self.assertAllCloseAccordingToType(var1_np, self.evaluate(var1))

  def testBasicWithLearningRateInverseTimeDecay(self):
    # TODO(tanzheny, omalleyt): Fix test in eager mode.
    for i, dtype in enumerate([tf.half, tf.float32, tf.float64]):
      with tf.Graph().as_default(), self.cached_session():
        # Initialize variables for numpy implementation.
        m0, v0, m1, v1 = 0.0, 0.0, 0.0, 0.0
        var0_np = np.array([1.0, 2.0], dtype=dtype.as_numpy_dtype)
        grads0_np = np.array([0.1, 0.1], dtype=dtype.as_numpy_dtype)
        var1_np = np.array([3.0, 4.0], dtype=dtype.as_numpy_dtype)
        grads1_np = np.array([0.01, 0.01], dtype=dtype.as_numpy_dtype)

        var0 = tf.Variable(var0_np, name="var0_%d" % i)
        var1 = tf.Variable(var1_np, name="var1_%d" % i)
        grads0 = tf.constant(grads0_np)
        grads1 = tf.constant(grads1_np)

        learning_rate = 0.001
        decay = 0.5
        lr_schedule = learning_rate_schedule.InverseTimeDecay(
            learning_rate, decay_steps=1.0, decay_rate=decay)
        beta_1 = 0.9
        beta_2 = 0.999
        epsilon = 1e-7

        opt = adam.Adam(
            learning_rate=lr_schedule,
            beta_1=beta_1,
            beta_2=beta_2,
            epsilon=epsilon)
        update = opt.apply_gradients(zip([grads0, grads1], [var0, var1]))

        self.evaluate(tf.compat.v1.global_variables_initializer())
        # Run 3 steps of Adam
        for t in range(3):
          self.evaluate(update)

          lr_np = learning_rate / (1 + decay * t)

          var0_np, m0, v0 = adam_update_numpy(
              var0_np, grads0_np, t, m0, v0, lr=lr_np)
          var1_np, m1, v1 = adam_update_numpy(
              var1_np, grads1_np, t, m1, v1, lr=lr_np)

          # Validate updated params
          self.assertAllCloseAccordingToType(var0_np, self.evaluate(var0))
          self.assertAllCloseAccordingToType(var1_np, self.evaluate(var1))

  def testTensorLearningRate(self):
    # TODO(tanzheny, omalleyt): Fix test in eager mode.
    for dtype in [tf.half, tf.float32, tf.float64]:
      with tf.Graph().as_default(), self.cached_session():
        # Initialize variables for numpy implementation.
        m0, v0, m1, v1 = 0.0, 0.0, 0.0, 0.0
        var0_np = np.array([1.0, 2.0], dtype=dtype.as_numpy_dtype)
        grads0_np = np.array([0.1, 0.1], dtype=dtype.as_numpy_dtype)
        var1_np = np.array([3.0, 4.0], dtype=dtype.as_numpy_dtype)
        grads1_np = np.array([0.01, 0.01], dtype=dtype.as_numpy_dtype)

        var0 = tf.Variable(var0_np)
        var1 = tf.Variable(var1_np)
        grads0 = tf.constant(grads0_np)
        grads1 = tf.constant(grads1_np)
        opt = adam.Adam(tf.constant(0.001))
        update = opt.apply_gradients(zip([grads0, grads1], [var0, var1]))
        self.evaluate(tf.compat.v1.global_variables_initializer())

        # Fetch params to validate initial values
        self.assertAllClose([1.0, 2.0], self.evaluate(var0))
        self.assertAllClose([3.0, 4.0], self.evaluate(var1))

        beta_1_power, beta_2_power = get_beta_accumulators(opt, dtype)
        # Run 3 steps of Adam
        for t in range(3):
          self.assertAllCloseAccordingToType(0.9**(t + 1),
                                             self.evaluate(beta_1_power))
          self.assertAllCloseAccordingToType(0.999**(t + 1),
                                             self.evaluate(beta_2_power))
          update.run()

          var0_np, m0, v0 = adam_update_numpy(var0_np, grads0_np, t, m0, v0)
          var1_np, m1, v1 = adam_update_numpy(var1_np, grads1_np, t, m1, v1)

          # Validate updated params
          self.assertAllCloseAccordingToType(var0_np, self.evaluate(var0))
          self.assertAllCloseAccordingToType(var1_np, self.evaluate(var1))

  def testSharing(self):
    # TODO(tanzheny, omalleyt): Fix test in eager mode.
    for dtype in [tf.half, tf.float32, tf.float64]:
      with tf.Graph().as_default(), self.cached_session():
        # Initialize variables for numpy implementation.
        m0, v0, m1, v1 = 0.0, 0.0, 0.0, 0.0
        var0_np = np.array([1.0, 2.0], dtype=dtype.as_numpy_dtype)
        grads0_np = np.array([0.1, 0.1], dtype=dtype.as_numpy_dtype)
        var1_np = np.array([3.0, 4.0], dtype=dtype.as_numpy_dtype)
        grads1_np = np.array([0.01, 0.01], dtype=dtype.as_numpy_dtype)

        var0 = tf.Variable(var0_np)
        var1 = tf.Variable(var1_np)
        grads0 = tf.constant(grads0_np)
        grads1 = tf.constant(grads1_np)
        opt = adam.Adam()
        update1 = opt.apply_gradients(zip([grads0, grads1], [var0, var1]))
        update2 = opt.apply_gradients(zip([grads0, grads1], [var0, var1]))
        self.evaluate(tf.compat.v1.global_variables_initializer())

        beta_1_power, beta_2_power = get_beta_accumulators(opt, dtype)

        # Fetch params to validate initial values
        self.assertAllClose([1.0, 2.0], self.evaluate(var0))
        self.assertAllClose([3.0, 4.0], self.evaluate(var1))

        # Run 3 steps of intertwined Adam1 and Adam2.
        for t in range(3):
          self.assertAllCloseAccordingToType(0.9**(t + 1),
                                             self.evaluate(beta_1_power))
          self.assertAllCloseAccordingToType(0.999**(t + 1),
                                             self.evaluate(beta_2_power))
          if t % 2 == 0:
            update1.run()
          else:
            update2.run()

          var0_np, m0, v0 = adam_update_numpy(var0_np, grads0_np, t, m0, v0)
          var1_np, m1, v1 = adam_update_numpy(var1_np, grads1_np, t, m1, v1)

          # Validate updated params
          self.assertAllCloseAccordingToType(var0_np, self.evaluate(var0))
          self.assertAllCloseAccordingToType(var1_np, self.evaluate(var1))

  @test_combinations.generate(test_combinations.combine(mode=["eager"]))
  def testSlotsUniqueEager(self):
    v1 = tf.Variable(1.)
    v2 = tf.Variable(1.)
    opt = adam.Adam(1.)
    opt.minimize(lambda: v1 + v2, var_list=[v1, v2])
    # There should be iteration, and two unique slot variables for v1 and v2.
    self.assertLen(set(v.ref() for v in opt.variables()), 5)
    self.assertEqual(
        self.evaluate(opt.variables()[0]), self.evaluate(opt.iterations))

  def testSetWeightsFromV1AdamWithoutMinimize(self):
    keras_v1_adam = optimizer_v1.Adam()
    keras_v2_adam = adam.Adam()
    keras_v2_adam.set_weights(keras_v1_adam.get_weights())
    keras_v1_iteration = keras_v1_adam.iterations
    keras_v2_iteration = keras_v2_adam.iterations
    self.evaluate(tf.compat.v1.global_variables_initializer())
    self.assertEqual(
        self.evaluate(keras_v1_iteration), self.evaluate(keras_v2_iteration))

  def testConstructAdamWithLR(self):
    opt = adam.Adam(lr=1.0)
    opt_2 = adam.Adam(learning_rate=0.1, lr=1.0)
    opt_3 = adam.Adam(learning_rate=0.1)
    self.assertIsInstance(opt.lr, tf.Variable)
    self.assertIsInstance(opt_2.lr, tf.Variable)
    self.assertIsInstance(opt_3.lr, tf.Variable)

    self.evaluate(tf.compat.v1.global_variables_initializer())
    self.assertAllClose(self.evaluate(opt.lr), (1.0))
    self.assertAllClose(self.evaluate(opt_2.lr), (1.0))
    self.assertAllClose(self.evaluate(opt_3.lr), (0.1))


class NonFusedAdamOptimizerTest(tf.test.TestCase, parameterized.TestCase):

  def testSparse(self):
    # TODO(tanzheny, omalleyt): Fix test in eager mode.
    for dtype in [tf.half, tf.float32, tf.float64]:
      with tf.Graph().as_default(), self.cached_session():
        # Initialize variables for numpy implementation.
        m0, v0, m1, v1 = 0.0, 0.0, 0.0, 0.0
        var0_np = np.array([1.0, 1.0, 2.0], dtype=dtype.as_numpy_dtype)
        grads0_np = np.array([0.1, 0.0, 0.1], dtype=dtype.as_numpy_dtype)
        var1_np = np.array([3.0, 3.0, 4.0], dtype=dtype.as_numpy_dtype)
        grads1_np = np.array([0.01, 0.0, 0.01], dtype=dtype.as_numpy_dtype)

        var0 = tf.Variable(var0_np)
        var1 = tf.Variable(var1_np)
        grads0_np_indices = np.array([0, 2], dtype=np.int32)
        grads0 = tf.IndexedSlices(
            tf.constant(grads0_np[grads0_np_indices]),
            tf.constant(grads0_np_indices), tf.constant([3]))
        grads1_np_indices = np.array([0, 2], dtype=np.int32)
        grads1 = tf.IndexedSlices(
            tf.constant(grads1_np[grads1_np_indices]),
            tf.constant(grads1_np_indices), tf.constant([3]))
        opt = adam.NonFusedAdam()
        update = opt.apply_gradients(zip([grads0, grads1], [var0, var1]))
        self.evaluate(tf.compat.v1.global_variables_initializer())

        # Fetch params to validate initial values
        self.assertAllClose([1.0, 1.0, 2.0], self.evaluate(var0))
        self.assertAllClose([3.0, 3.0, 4.0], self.evaluate(var1))

        beta_1_power, beta_2_power = get_beta_accumulators(opt, dtype)
        # Run 3 steps of NonFusedAdam
        for t in range(3):
          self.assertAllCloseAccordingToType(0.9**(t + 1),
                                             self.evaluate(beta_1_power))
          self.assertAllCloseAccordingToType(0.999**(t + 1),
                                             self.evaluate(beta_2_power))
          update.run()

          var0_np, m0, v0 = adam_update_numpy(var0_np, grads0_np, t, m0, v0)
          var1_np, m1, v1 = adam_update_numpy(var1_np, grads1_np, t, m1, v1)

          # Validate updated params
          self.assertAllCloseAccordingToType(var0_np, self.evaluate(var0))
          self.assertAllCloseAccordingToType(var1_np, self.evaluate(var1))

  def testSparseDevicePlacement(self):
    # TODO(tanzheny, omalleyt): Fix test in eager mode.
    for index_dtype in [tf.int32, tf.int64]:
      with tf.Graph().as_default(), self.cached_session(
          force_gpu=tf.test.is_gpu_available()):
        # If a GPU is available, tests that all optimizer ops can be placed on
        # it (i.e. they have GPU kernels).
        var = tf.Variable([[1.0], [2.0]])
        indices = tf.constant([0, 1], dtype=index_dtype)
        g_sum = lambda: tf.reduce_sum(tf.gather(var, indices))  # pylint: disable=cell-var-from-loop
        optimizer = adam.NonFusedAdam(3.0)
        minimize_op = optimizer.minimize(g_sum, var_list=[var])
        self.evaluate(tf.compat.v1.global_variables_initializer())
        minimize_op.run()

  def testSparseRepeatedIndices(self):
    # TODO(tanzheny, omalleyt): Fix test in eager mode.
    for dtype in [tf.half, tf.float32, tf.float64]:
      with tf.Graph().as_default(), self.cached_session():
        repeated_index_update_var = tf.Variable(
            [[1.0], [2.0]], dtype=dtype)
        aggregated_update_var = tf.Variable(
            [[1.0], [2.0]], dtype=dtype)
        grad_repeated_index = tf.IndexedSlices(
            tf.constant(
                [0.1, 0.1], shape=[2, 1], dtype=dtype),
            tf.constant([1, 1]),
            tf.constant([2, 1]))
        grad_aggregated = tf.IndexedSlices(
            tf.constant(
                [0.2], shape=[1, 1], dtype=dtype),
            tf.constant([1]),
            tf.constant([2, 1]))
        repeated_update = adam.NonFusedAdam().apply_gradients(
            [(grad_repeated_index, repeated_index_update_var)])
        aggregated_update = adam.NonFusedAdam().apply_gradients(
            [(grad_aggregated, aggregated_update_var)])
        self.evaluate(tf.compat.v1.global_variables_initializer())
        self.assertAllClose(aggregated_update_var,
                            self.evaluate(repeated_index_update_var))
        for _ in range(3):
          repeated_update.run()
          aggregated_update.run()
          self.assertAllClose(aggregated_update_var,
                              self.evaluate(repeated_index_update_var))

  def doTestBasic(self, use_callable_params=False):
    for i, dtype in enumerate([tf.half, tf.float32, tf.float64]):
      with self.cached_session():
        # Initialize variables for numpy implementation.
        m0, v0, m1, v1 = 0.0, 0.0, 0.0, 0.0
        var0_np = np.array([1.0, 2.0], dtype=dtype.as_numpy_dtype)
        grads0_np = np.array([0.1, 0.1], dtype=dtype.as_numpy_dtype)
        var1_np = np.array([3.0, 4.0], dtype=dtype.as_numpy_dtype)
        grads1_np = np.array([0.01, 0.01], dtype=dtype.as_numpy_dtype)

        var0 = tf.Variable(var0_np, name="var0_%d" % i)
        var1 = tf.Variable(var1_np, name="var1_%d" % i)
        grads0 = tf.constant(grads0_np)
        grads1 = tf.constant(grads1_np)

        learning_rate = lambda: 0.001
        beta1 = lambda: 0.9
        beta2 = lambda: 0.999
        epsilon = lambda: 1e-8
        if not use_callable_params:
          learning_rate = learning_rate()
          beta1 = beta1()
          beta2 = beta2()
          epsilon = epsilon()

        opt = adam.NonFusedAdam(learning_rate=learning_rate)
        if not tf.executing_eagerly():
          update = opt.apply_gradients(zip([grads0, grads1], [var0, var1]))

        self.evaluate(tf.compat.v1.global_variables_initializer())
        # Run 3 steps of NonFusedAdam
        for t in range(3):
          beta_1_power, beta_2_power = get_beta_accumulators(opt, dtype)
          self.assertAllCloseAccordingToType(0.9**(t + 1),
                                             self.evaluate(beta_1_power))
          self.assertAllCloseAccordingToType(0.999**(t + 1),
                                             self.evaluate(beta_2_power))
          if not tf.executing_eagerly():
            self.evaluate(update)
          else:
            opt.apply_gradients(zip([grads0, grads1], [var0, var1]))

          var0_np, m0, v0 = adam_update_numpy(var0_np, grads0_np, t, m0, v0)
          var1_np, m1, v1 = adam_update_numpy(var1_np, grads1_np, t, m1, v1)

          # Validate updated params
          self.assertAllCloseAccordingToType(
              var0_np, self.evaluate(var0), rtol=1e-4, atol=1e-4)
          self.assertAllCloseAccordingToType(
              var1_np, self.evaluate(var1), rtol=1e-4, atol=1e-4)

  @test_combinations.generate(
      test_combinations.combine(mode=["graph", "eager"]))
  def testResourceBasic(self):
    self.doTestBasic()

  @test_combinations.generate(test_combinations.combine(mode=["eager"]))
  def testBasicCallableParams(self):
    self.doTestBasic(use_callable_params=True)

  @test_combinations.generate(
      test_combinations.combine(mode=["graph", "eager"]))
  def testBasicWithAmsgrad(self):
    for i, dtype in enumerate([tf.half, tf.float32, tf.float64]):
      with self.cached_session():
        # Initialize variables for numpy implementation.
        m0, v0, v0hat, m1, v1, v1hat = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
        var0_np = np.array([1.0, 2.0], dtype=dtype.as_numpy_dtype)
        grads0_np = np.array([0.1, 0.1], dtype=dtype.as_numpy_dtype)
        var1_np = np.array([3.0, 4.0], dtype=dtype.as_numpy_dtype)
        grads1_np = np.array([0.01, 0.01], dtype=dtype.as_numpy_dtype)

        var0 = tf.Variable(var0_np, name="var0_%d" % i)
        var1 = tf.Variable(var1_np, name="var1_%d" % i)
        grads0 = tf.constant(grads0_np)
        grads1 = tf.constant(grads1_np)

        opt = adam.NonFusedAdam(amsgrad=True)
        if not tf.executing_eagerly():
          update = opt.apply_gradients(zip([grads0, grads1], [var0, var1]))

        self.evaluate(tf.compat.v1.global_variables_initializer())
        # Run 3 steps of NonFusedAdam
        for t in range(3):
          beta_1_power, beta_2_power = get_beta_accumulators(opt, dtype)
          self.assertAllCloseAccordingToType(0.9**(t + 1),
                                             self.evaluate(beta_1_power))
          self.assertAllCloseAccordingToType(0.999**(t + 1),
                                             self.evaluate(beta_2_power))
          if not tf.executing_eagerly():
            self.evaluate(update)
          else:
            opt.apply_gradients(zip([grads0, grads1], [var0, var1]))

          var0_np, m0, v0, v0hat = adam_update_numpy_amsgrad(
              var0_np, grads0_np, t, m0, v0, v0hat)
          var1_np, m1, v1, v1hat = adam_update_numpy_amsgrad(
              var1_np, grads1_np, t, m1, v1, v1hat)

          # Validate updated params
          self.assertAllCloseAccordingToType(
              var0_np, self.evaluate(var0), rtol=1e-4, atol=1e-4)
          self.assertAllCloseAccordingToType(
              var1_np, self.evaluate(var1), rtol=1e-4, atol=1e-4)

  @test_combinations.generate(
      test_combinations.combine(mode=["graph", "eager"]))
  def testSparseWithAmsgrad(self):
    # dtypes.half does not work on gpu + eager.
    for dtype in [tf.float32, tf.float64]:
      with self.cached_session():
        m0 = np.array([[0.0], [0.0]])
        v0 = np.array([[0.0], [0.0]])
        v0hat = np.array([[0.0], [0.0]])
        indices_np = np.array([1])
        indices = tf.constant(indices_np, dtype=tf.int32)
        var0_np = np.array([[1.0], [2.0]], dtype=dtype.as_numpy_dtype)
        repeated_index_update_var = tf.Variable(var0_np, dtype=dtype)
        aggregated_update_var = tf.Variable(var0_np, dtype=dtype)
        grads0_np = np.array([[0.2]], dtype=dtype.as_numpy_dtype)
        grad_repeated_index = tf.IndexedSlices(
            tf.constant([0.1, 0.1], shape=[2, 1], dtype=dtype),
            tf.constant([1, 1]), tf.constant([2, 1]))
        grad_aggregated = tf.IndexedSlices(grads0_np, indices,
                                            tf.constant([2, 1]))
        opt_repeated = adam.NonFusedAdam(amsgrad=True)
        opt_aggregated = adam.NonFusedAdam(amsgrad=True)
        if not tf.executing_eagerly():
          repeated_update = opt_repeated.apply_gradients(
              [(grad_repeated_index, repeated_index_update_var)])
          aggregated_update = opt_aggregated.apply_gradients(
              [(grad_aggregated, aggregated_update_var)])
        self.evaluate(tf.compat.v1.global_variables_initializer())
        self.assertAllClose(
            self.evaluate(aggregated_update_var),
            self.evaluate(repeated_index_update_var))
        for t in range(3):
          if not tf.executing_eagerly():
            self.evaluate(repeated_update)
            self.evaluate(aggregated_update)
          else:
            opt_repeated.apply_gradients(
                [(grad_repeated_index, repeated_index_update_var)])
            opt_aggregated.apply_gradients(
                [(grad_aggregated, aggregated_update_var)])

          var0_np, m0, v0, v0hat = adam_sparse_update_numpy_amsgrad(
              var0_np, indices_np, grads0_np, t, m0, v0, v0hat)

          # Validate updated params
          self.assertAllCloseAccordingToType(
              var0_np, self.evaluate(aggregated_update_var))
          self.assertAllCloseAccordingToType(
              self.evaluate(aggregated_update_var),
              self.evaluate(repeated_index_update_var))

  def testBasicWithLearningRateDecay(self):
    # TODO(tanzheny, omalleyt): Fix test in eager mode.
    for i, dtype in enumerate([tf.half, tf.float32, tf.float64]):
      with tf.Graph().as_default(), self.cached_session():
        # Initialize variables for numpy implementation.
        m0, v0, m1, v1 = 0.0, 0.0, 0.0, 0.0
        var0_np = np.array([1.0, 2.0], dtype=dtype.as_numpy_dtype)
        grads0_np = np.array([0.1, 0.1], dtype=dtype.as_numpy_dtype)
        var1_np = np.array([3.0, 4.0], dtype=dtype.as_numpy_dtype)
        grads1_np = np.array([0.01, 0.01], dtype=dtype.as_numpy_dtype)

        var0 = tf.Variable(var0_np, name="var0_%d" % i)
        var1 = tf.Variable(var1_np, name="var1_%d" % i)
        grads0 = tf.constant(grads0_np)
        grads1 = tf.constant(grads1_np)

        learning_rate = 0.001
        beta_1 = 0.9
        beta_2 = 0.999
        epsilon = 1e-7
        decay = 0.5

        opt = adam.NonFusedAdam(
            learning_rate=learning_rate,
            beta_1=beta_1,
            beta_2=beta_2,
            epsilon=epsilon,
            decay=decay)
        update = opt.apply_gradients(zip([grads0, grads1], [var0, var1]))

        self.evaluate(tf.compat.v1.global_variables_initializer())
        # Run 3 steps of NonFusedAdam
        for t in range(3):
          self.evaluate(update)
          lr_np = learning_rate / (1 + decay * t)

          var0_np, m0, v0 = adam_update_numpy(
              var0_np, grads0_np, t, m0, v0, lr=lr_np)
          var1_np, m1, v1 = adam_update_numpy(
              var1_np, grads1_np, t, m1, v1, lr=lr_np)

          # Validate updated params
          self.assertAllCloseAccordingToType(var0_np, self.evaluate(var0))
          self.assertAllCloseAccordingToType(var1_np, self.evaluate(var1))

  def testBasicWithLearningRateInverseTimeDecay(self):
    # TODO(tanzheny, omalleyt): Fix test in eager mode.
    for i, dtype in enumerate([tf.half, tf.float32, tf.float64]):
      with tf.Graph().as_default(), self.cached_session():
        # Initialize variables for numpy implementation.
        m0, v0, m1, v1 = 0.0, 0.0, 0.0, 0.0
        var0_np = np.array([1.0, 2.0], dtype=dtype.as_numpy_dtype)
        grads0_np = np.array([0.1, 0.1], dtype=dtype.as_numpy_dtype)
        var1_np = np.array([3.0, 4.0], dtype=dtype.as_numpy_dtype)
        grads1_np = np.array([0.01, 0.01], dtype=dtype.as_numpy_dtype)

        var0 = tf.Variable(var0_np, name="var0_%d" % i)
        var1 = tf.Variable(var1_np, name="var1_%d" % i)
        grads0 = tf.constant(grads0_np)
        grads1 = tf.constant(grads1_np)

        learning_rate = 0.001
        decay = 0.5
        lr_schedule = learning_rate_schedule.InverseTimeDecay(
            learning_rate, decay_steps=1.0, decay_rate=decay)
        beta_1 = 0.9
        beta_2 = 0.999
        epsilon = 1e-7

        opt = adam.NonFusedAdam(
            learning_rate=lr_schedule,
            beta_1=beta_1,
            beta_2=beta_2,
            epsilon=epsilon)
        update = opt.apply_gradients(zip([grads0, grads1], [var0, var1]))

        self.evaluate(tf.compat.v1.global_variables_initializer())
        # Run 3 steps of NonFusedAdam
        for t in range(3):
          self.evaluate(update)

          lr_np = learning_rate / (1 + decay * t)

          var0_np, m0, v0 = adam_update_numpy(
              var0_np, grads0_np, t, m0, v0, lr=lr_np)
          var1_np, m1, v1 = adam_update_numpy(
              var1_np, grads1_np, t, m1, v1, lr=lr_np)

          # Validate updated params
          self.assertAllCloseAccordingToType(var0_np, self.evaluate(var0))
          self.assertAllCloseAccordingToType(var1_np, self.evaluate(var1))

  def testTensorLearningRate(self):
    # TODO(tanzheny, omalleyt): Fix test in eager mode.
    for dtype in [tf.half, tf.float32, tf.float64]:
      with tf.Graph().as_default(), self.cached_session():
        # Initialize variables for numpy implementation.
        m0, v0, m1, v1 = 0.0, 0.0, 0.0, 0.0
        var0_np = np.array([1.0, 2.0], dtype=dtype.as_numpy_dtype)
        grads0_np = np.array([0.1, 0.1], dtype=dtype.as_numpy_dtype)
        var1_np = np.array([3.0, 4.0], dtype=dtype.as_numpy_dtype)
        grads1_np = np.array([0.01, 0.01], dtype=dtype.as_numpy_dtype)

        var0 = tf.Variable(var0_np)
        var1 = tf.Variable(var1_np)
        grads0 = tf.constant(grads0_np)
        grads1 = tf.constant(grads1_np)
        opt = adam.NonFusedAdam(tf.constant(0.001))
        update = opt.apply_gradients(zip([grads0, grads1], [var0, var1]))
        self.evaluate(tf.compat.v1.global_variables_initializer())

        # Fetch params to validate initial values
        self.assertAllClose([1.0, 2.0], self.evaluate(var0))
        self.assertAllClose([3.0, 4.0], self.evaluate(var1))

        beta_1_power, beta_2_power = get_beta_accumulators(opt, dtype)
        # Run 3 steps of NonFusedAdam
        for t in range(3):
          self.assertAllCloseAccordingToType(0.9**(t + 1),
                                             self.evaluate(beta_1_power))
          self.assertAllCloseAccordingToType(0.999**(t + 1),
                                             self.evaluate(beta_2_power))
          update.run()

          var0_np, m0, v0 = adam_update_numpy(var0_np, grads0_np, t, m0, v0)
          var1_np, m1, v1 = adam_update_numpy(var1_np, grads1_np, t, m1, v1)

          # Validate updated params
          self.assertAllCloseAccordingToType(var0_np, self.evaluate(var0))
          self.assertAllCloseAccordingToType(var1_np, self.evaluate(var1))

  def testSharing(self):
    # TODO(tanzheny, omalleyt): Fix test in eager mode.
    for dtype in [tf.half, tf.float32, tf.float64]:
      with tf.Graph().as_default(), self.cached_session():
        # Initialize variables for numpy implementation.
        m0, v0, m1, v1 = 0.0, 0.0, 0.0, 0.0
        var0_np = np.array([1.0, 2.0], dtype=dtype.as_numpy_dtype)
        grads0_np = np.array([0.1, 0.1], dtype=dtype.as_numpy_dtype)
        var1_np = np.array([3.0, 4.0], dtype=dtype.as_numpy_dtype)
        grads1_np = np.array([0.01, 0.01], dtype=dtype.as_numpy_dtype)

        var0 = tf.Variable(var0_np)
        var1 = tf.Variable(var1_np)
        grads0 = tf.constant(grads0_np)
        grads1 = tf.constant(grads1_np)
        opt = adam.NonFusedAdam()
        update1 = opt.apply_gradients(zip([grads0, grads1], [var0, var1]))
        update2 = opt.apply_gradients(zip([grads0, grads1], [var0, var1]))
        self.evaluate(tf.compat.v1.global_variables_initializer())

        beta_1_power, beta_2_power = get_beta_accumulators(opt, dtype)

        # Fetch params to validate initial values
        self.assertAllClose([1.0, 2.0], self.evaluate(var0))
        self.assertAllClose([3.0, 4.0], self.evaluate(var1))

        # Run 3 steps of intertwined NonFusedAdam1 and NonFusedAdam2.
        for t in range(3):
          self.assertAllCloseAccordingToType(0.9**(t + 1),
                                             self.evaluate(beta_1_power))
          self.assertAllCloseAccordingToType(0.999**(t + 1),
                                             self.evaluate(beta_2_power))
          if t % 2 == 0:
            update1.run()
          else:
            update2.run()

          var0_np, m0, v0 = adam_update_numpy(var0_np, grads0_np, t, m0, v0)
          var1_np, m1, v1 = adam_update_numpy(var1_np, grads1_np, t, m1, v1)

          # Validate updated params
          self.assertAllCloseAccordingToType(var0_np, self.evaluate(var0))
          self.assertAllCloseAccordingToType(var1_np, self.evaluate(var1))


if __name__ == "__main__":
  tf.test.main()
