import tensorflow as tf
from tensorflow.python.ops.distributions.categorical import Categorical
from tensorflow.python.ops.rnn import _transpose_batch_time
from tensorflow.python.ops.rnn_cell_impl import LSTMStateTuple, LSTMCell

from utils.slstm import BasicSLSTMCell


def model_fn(features, labels, mode, params):
    X_s, X_r, X_u = features

    cur_batch_B = tf.shape(X_s)[0]
    cur_batch_T = tf.shape(X_s)[1]
    cur_batch_D = params.num_char

    Xs_embd = tf.one_hot(X_s, cur_batch_D)
    X_ta = tf.TensorArray(size=cur_batch_T, dtype=tf.float32).unstack(
        _transpose_batch_time(Xs_embd), 'TBD_Formatted_X')

    acell = {
        'lstm': lambda: LSTMCell(params.num_hidden),
        'sru': lambda: BasicSLSTMCell(params.num_hidden)
    }[params.cell]()

    output_layer_info = {
        'units': cur_batch_D,  # this is the size of vocabulary
        'name': 'out_to_character',
        # linear 'activation': tf.nn.softmax
    }

    with tf.variable_scope('Shared_Dense', reuse=False) as dense_layer_scope:
        # this will be replaced by the cell_output later
        zeros_placeholder = tf.zeros([1, acell.output_size])
        tf.layers.dense(zeros_placeholder, **output_layer_info)

    def get_logits(cell_out):
        # useful when measuring the cross-entropy loss
        with tf.variable_scope(dense_layer_scope, reuse=True):
            return tf.layers.dense(cell_out, **output_layer_info)

    def get_dist(cell_out):
        return Categorical(logits=get_logits(cell_out), name='categorical_dist', allow_nan_stats=False,
                           dtype=tf.int32)

    def get_sample(cell_out):
        return tf.one_hot(get_dist(cell_out).sample(), cur_batch_D)

    def get_prob(cell_out, obs):
        # the observation is in
        return get_dist(cell_out).prob(obs)

    with tf.variable_scope('Initial_State'):
        h_init = tf.tile(tf.get_variable('init_state_h', [1, params.num_hidden],
                                         initializer=tf.random_uniform_initializer(0)),
                         [cur_batch_B, 1])
        c_init = tf.tile(tf.get_variable('init_state_c', [1, params.num_hidden],
                                         initializer=tf.random_uniform_initializer(0)),
                         [cur_batch_B, 1])
        cell_init_state = LSTMStateTuple(c_init, h_init)

        first_step = tf.zeros(shape=[cur_batch_B, cur_batch_D], dtype=tf.float32, name='first_character')

    with tf.name_scope('NADE'):
        output_ta = tf.TensorArray(size=cur_batch_T, dtype=tf.float32)

        def loop_fn(time, cell_output, cell_state, loop_state):
            emit_output = cell_output  # == None for time == 0

            if cell_output is None:
                next_cell_state = cell_init_state
                next_step = first_step
                next_loop_state = output_ta
            else:  # pass the last state to the next
                next_cell_state = cell_state
                next_step = X_ta.read(time - 1) if mode == tf.estimator.ModeKeys.TRAIN else get_sample(cell_output)
                next_loop_state = loop_state.write(time - 1, next_step)

            elements_finished = (time >= cur_batch_T)

            return elements_finished, next_step, next_cell_state, emit_output, next_loop_state

        output_ta, _, loop_state_ta = tf.nn.raw_rnn(acell, loop_fn)

    with tf.name_scope('Output'):
        outputs = _transpose_batch_time(output_ta.stack())
        logits = get_logits(outputs)
        X_sampled = _transpose_batch_time(loop_state_ta.stack())
        logp_loss = -tf.reduce_mean(tf.log(1e-6 + get_prob(outputs, X_s)), name='model_loss')
        xentropy_loss = tf.reduce_mean(
            tf.nn.sigmoid_cross_entropy_with_logits(labels=Xs_embd, logits=logits))

    train_op = tf.train.RMSPropOptimizer(learning_rate=params.learning_rate).minimize(
        loss=logp_loss, global_step=tf.train.get_global_step())

    return tf.estimator.EstimatorSpec(
        mode=mode,
        predictions=X_sampled,
        loss=logp_loss,
        train_op=train_op)