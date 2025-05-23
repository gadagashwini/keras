# Description:
#   Contains the Keras normalization layers (internal TensorFlow version).

load("@org_keras//keras:keras.bzl", "cuda_py_test")

package(
    # TODO(scottzhu): Remove non-keras deps from TF.
    default_visibility = [
        "//keras:friends",
        "//third_party/tensorflow/python/distribute:__pkg__",
        "//third_party/tensorflow/python/feature_column:__pkg__",
        "//third_party/tensorflow/python/training/tracking:__pkg__",
        "//third_party/tensorflow/tools/pip_package:__pkg__",
        "//third_party/tensorflow_models/official/projects/residual_mobilenet/modeling/backbones:__pkg__",
    ],
    licenses = ["notice"],
)

py_library(
    name = "normalization",
    srcs = [
        "__init__.py",
    ],
    srcs_version = "PY3",
    deps = [
        ":batch_normalization",
        ":batch_normalization_v1",
        ":layer_normalization",
        ":unit_normalization",
    ],
)

py_library(
    name = "batch_normalization",
    srcs = ["batch_normalization.py"],
    srcs_version = "PY3",
    deps = [
        "//:expect_tensorflow_installed",
        "//keras:backend",
        "//keras:constraints",
        "//keras:regularizers",
        "//keras/engine:base_layer",
        "//keras/engine:input_spec",
        "//keras/initializers",
        "//keras/utils:control_flow_util",
    ],
)

py_library(
    name = "batch_normalization_v1",
    srcs = ["batch_normalization_v1.py"],
    srcs_version = "PY3",
    deps = [
        ":batch_normalization",
        "//:expect_tensorflow_installed",
    ],
)

py_library(
    name = "layer_normalization",
    srcs = ["layer_normalization.py"],
    srcs_version = "PY3",
    deps = [
        "//:expect_tensorflow_installed",
        "//keras:constraints",
        "//keras:regularizers",
        "//keras/engine:base_layer",
        "//keras/initializers",
    ],
)

py_library(
    name = "unit_normalization",
    srcs = ["unit_normalization.py"],
    srcs_version = "PY3",
    deps = [
        "//:expect_tensorflow_installed",
        "//keras/engine:base_layer",
    ],
)

cuda_py_test(
    name = "batch_normalization_test",
    size = "medium",
    srcs = ["batch_normalization_test.py"],
    python_version = "PY3",
    shard_count = 4,
    tags = [
        "notsan",
    ],
    deps = [
        ":batch_normalization",
        "//:expect_absl_installed",
        "//:expect_numpy_installed",
        "//:expect_tensorflow_installed",
        "//keras",
        "//keras/layers",
        "//keras/testing_infra:test_combinations",
        "//keras/testing_infra:test_utils",
    ],
)

cuda_py_test(
    name = "layer_normalization_test",
    size = "medium",
    srcs = ["layer_normalization_test.py"],
    python_version = "PY3",
    shard_count = 4,
    tags = [
        "notsan",
    ],
    deps = [
        "//:expect_absl_installed",
        "//:expect_numpy_installed",
        "//:expect_tensorflow_installed",
        "//keras",
        "//keras/testing_infra:test_combinations",
    ],
)

cuda_py_test(
    name = "unit_normalization_test",
    size = "small",
    srcs = ["unit_normalization_test.py"],
    python_version = "PY3",
    deps = [
        "//:expect_absl_installed",
        "//:expect_numpy_installed",
        "//:expect_tensorflow_installed",
        "//keras",
        "//keras/testing_infra:test_combinations",
    ],
)
