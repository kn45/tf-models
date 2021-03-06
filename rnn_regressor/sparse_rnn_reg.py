#!/usr/bin/env python

import random
import numpy as np
import sys
import tensorflow as tf
import time


class RNNRegressor(object):
    """RNN(LSTM/GRU etc.) Regressor
    """
    def __init__(self, vocab_size, emb_dim=200, hid_dim=128, nclass=1,
                 time_len=40, pad_id=0, one_hot=False, cellt='LSTM',
                 nlayer=1, reg_lambda=0, lr=None, init_embed=None,
                 emb_trainable=True, keep_prob=1.0):
        self.TIME_LEN = time_len  # max time-series length
        self.PAD_ID = pad_id  # 0

        # prepare input and output placeholder
        self.inp_x = tf.placeholder(tf.int32, [None, self.TIME_LEN], 'input_x')
        self.inp_y = tf.placeholder(tf.float32, [None, nclass], 'input_y')
        inp_len = tf.reduce_sum(tf.sign(self.inp_x), reduction_indices=1)

        # embedding
        if one_hot:
            inp_emb = tf.nn.embedding_lookup(
                np.identity(vocab_size, dtype=np.float32), self.inp_x)
            emb_dim = vocab_size
        else:
            if init_embed is not None:
                embedding = tf.Variable(
                    tf.convert_to_tensor(init_embed, dtype=tf.float32),
                    trainable=emb_trainable, name='embedding')
            else:
                embedding = tf.get_variable(
                    'embedding', shape=[vocab_size, emb_dim],
                    initializer=tf.random_uniform_initializer(
                        minval=-0.2,
                        maxval=0.2,
                        dtype=tf.float32))
            inp_emb = tf.nn.embedding_lookup(embedding, self.inp_x)

        # construct basic cell
        if cellt == 'LSTM':
            cell = tf.nn.rnn_cell.LSTMCell(
                num_units=hid_dim,
                initializer=tf.random_uniform_initializer(
                    minval=-1./emb_dim**0.5,
                    maxval=+1./emb_dim**0.5))
        elif cellt == 'GRU':
            cell = tf.nn.rnn_cell.GRUCell(num_units=hid_dim)
        elif cellt == 'BasicRNN':
            cell = tf.nn.rnn_cell.BasicRNNCell(num_units=hid_dim)
        else:
            sys.stderr.write('invalid cell type')
            sys.exit(1)

        # layers
        if nlayer > 1:
            cell = tf.nn.rnn_cell.MultiRNNCell(cells=[cell] * nlayer)

        # dropout
        # set keep_prob = 1.0 when predicting
        cell = tf.nn.rnn_cell.DropoutWrapper(
            cell, output_keep_prob=keep_prob, input_keep_prob=keep_prob)

        # construct rnn
        outputs, states = tf.nn.dynamic_rnn(
            cell=cell,
            dtype=tf.float32,
            sequence_length=inp_len,
            inputs=inp_emb)

        # extract res from dynamic series by given series_length
        batch_size = tf.shape(outputs)[0]  # [batch_size, time_len, dimension]
        oup_idx = tf.range(0, batch_size) * self.TIME_LEN + (inp_len - 1)
        oup_flat = tf.reshape(outputs, [-1, hid_dim])  # [batch*time_len, dim]
        oup_rnn = tf.gather(oup_flat, oup_idx)

        # make prediction
        w = tf.get_variable(
            'W', shape=[hid_dim, nclass],
            initializer=tf.contrib.layers.xavier_initializer())
        b = tf.Variable(tf.constant(0.1, shape=[nclass]), name='b')
        self.preds = tf.add(tf.matmul(oup_rnn, w), b, name='prediction')

        # calculate loss
        self.loss = tf.sqrt(
            tf.reduce_mean(tf.square(tf.sub(self.inp_y, self.preds))))  # rmse
        reg_loss = reg_lambda * (tf.nn.l2_loss(w) + tf.nn.l2_loss(b))  # l2 reg
        self.total_loss = self.loss + reg_loss

        # bptt
        if lr:
            self.opt = tf.train.AdamOptimizer(
                learning_rate=lr).minimize(self.total_loss)
        else:
            self.opt = tf.train.AdamOptimizer().minimize(self.total_loss)
        # self.opt = tf.train.AdadeltaOptimizer().minimize(self.total_loss)

    def pred(self, sess, input_x):
        pred_dict = {self.inp_x: input_x}
        return sess.run(self.preds, feed_dict=pred_dict)

    def evals(self, sess, dev_x, dev_y):
        evals_dict = {self.inp_x: dev_x, self.inp_y: dev_y}
        return self.loss.eval(feed_dict=evals_dict, session=sess)

    def train_step(self, sess, inp_batch_x, inp_batch_y, evals=None):
        input_dict = {self.inp_x: inp_batch_x, self.inp_y: inp_batch_y}
        sess.run(self.opt, feed_dict=input_dict)

        # evaluation
        if evals:
            evlstr = ''
            for evl in evals:
                if random.random() < evl[1]:
                    loss = self.evals(sess, evl[2], evl[3])
                    evlstr += evl[0] + ': ' + str(loss) + '\t\t'
                else:
                    evlstr += evl[0] + ': skipt\t'
            print evlstr
            sys.stdout.flush()

    def padding(self, input_x):
        inp_x = []
        for rec in input_x:
            nrec = rec[:self.TIME_LEN] + \
                [self.PAD_ID] * (self.TIME_LEN - len(rec))
            inp_x.append(np.array(nrec, dtype=np.int32))
        return np.array(inp_x)

    def get_pad_batch(self, data, batch_size=1):
        inp_x, inp_y = [], []
        for _ in xrange(batch_size):
            raw_y, raw_x = random.choice(data)
            inp_y.append(np.array(raw_y, dtype=np.float32))
            raw_x = raw_x[:self.TIME_LEN] + \
                [self.PAD_ID] * (self.TIME_LEN - len(raw_x))
            inp_x.append(np.array(raw_x, dtype=np.int32))
        return np.array(inp_x), np.array(inp_y)

if __name__ == '__main__':
    mdl_lstm = RNNRegressor(
        vocab_size=10,
        emb_dim=4,
        hid_dim=100,
        nclass=1,
        time_len=40,
        pad_id=0,
        cellt='LSTM')

    # mdl_lstm.test()
    inp_data = [[[0.033], [1, 3, 4, 5, 8]],
                [[0.092], [2, 6, 3, 4, 8, 6]],
                [[0.047], [5, 5, 7, 1, 6]]]

    evals = [['train', 1.0, data_inp_x, data_inp_y]]

    sess = tf.InteractiveSession()
    sess.run(tf.initialize_all_variables())
    for _ in range(50):
        data_inp_x, data_inp_y = mdl_lstm.get_pad_batch(inp_data, 3)
        print data_inp_x
        print data_inp_y
        mdl_lstm.train_step(sess, data_inp_x, data_inp_y, evals)
    sess.close()
