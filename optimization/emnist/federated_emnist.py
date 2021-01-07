# Copyright 2019, Google LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Federated EMNIST character recognition library using TFF."""

import functools

import tensorflow as tf
import tensorflow_federated as tff

from optimization.shared import training_specs
from utils import training_utils
from utils.datasets import emnist_dataset
from utils.models import emnist_models

EMNIST_MODELS = ['cnn', '2nn']


def configure_training(task_spec: training_specs.TaskSpec,
                       model: str = 'cnn') -> training_specs.RunnerSpec:
  """Configures training for the EMNIST character recognition task.

  This method will load and pre-process datasets and construct a model used for
  the task. It then uses `iterative_process_builder` to create an iterative
  process compatible with `federated_research.utils.training_loop`.

  Args:
    task_spec: A `TaskSpec` class for creating federated training tasks.
    model: A string specifying the model used for character recognition. Can be
      one of `cnn` and `2nn`, corresponding to a CNN model and a densely
      connected 2-layer model (respectively).

  Returns:
    A `RunnerSpec` containing attributes used for running the newly created
    federated task.
  """

  emnist_train, _ = emnist_dataset.get_federated_datasets(
      train_client_batch_size=task_spec.client_batch_size,
      train_client_epochs_per_round=task_spec.client_epochs_per_round,
      only_digits=False)

  _, emnist_test = emnist_dataset.get_centralized_datasets(only_digits=False)

  input_spec = emnist_train.create_tf_dataset_for_client(
      emnist_train.client_ids[0]).element_spec

  if model == 'cnn':
    model_builder = functools.partial(
        emnist_models.create_conv_dropout_model, only_digits=False)
  elif model == '2nn':
    model_builder = functools.partial(
        emnist_models.create_two_hidden_layer_model, only_digits=False)
  else:
    raise ValueError(
        'Cannot handle model flag [{!s}], must be one of {!s}.'.format(
            model, EMNIST_MODELS))

  loss_builder = tf.keras.losses.SparseCategoricalCrossentropy
  metrics_builder = lambda: [tf.keras.metrics.SparseCategoricalAccuracy()]

  def tff_model_fn() -> tff.learning.Model:
    return tff.learning.from_keras_model(
        keras_model=model_builder(),
        input_spec=input_spec,
        loss=loss_builder(),
        metrics=metrics_builder())

  training_process = task_spec.iterative_process_builder(tff_model_fn)

  client_datasets_fn = training_utils.build_client_datasets_fn(
      dataset=emnist_train,
      clients_per_round=task_spec.clients_per_round,
      random_seed=task_spec.client_datasets_random_seed)

  test_fn = training_utils.build_centralized_evaluate_fn(
      eval_dataset=emnist_test,
      model_builder=model_builder,
      loss_builder=loss_builder,
      metrics_builder=metrics_builder)

  validation_fn = lambda model_weights, round_num: test_fn(model_weights)

  return training_specs.RunnerSpec(
      iterative_process=training_process,
      client_datasets_fn=client_datasets_fn,
      validation_fn=validation_fn,
      test_fn=test_fn)
