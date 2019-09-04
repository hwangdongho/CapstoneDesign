"""Imports a model metagraph and checkpoint file, converts the variables to constants
and exports the model as a graphdef protobuf
"""
# MIT License
# 
# Copyright (c) 2016 David Sandberg
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from tensorflow.python.framework import graph_util
import tensorflow as tf
import argparse
import os
import sys
import facenet
from six.moves import xrange  # @UnresolvedImport

class make_pb:
    def __init__(self, model_dir, output_file):
        self.model_dir = model_dir
        self.output_file = output_file
        
        with tf.Graph().as_default():
            with tf.compat.v1.Session() as sess:
                # Load the model metagraph and checkpoint
                print('Model directory: %s' % self.model_dir)
                meta_file, ckpt_file = facenet.get_model_filenames(os.path.expanduser(self.model_dir))
                
                print('Metagraph file: %s' % meta_file)
                print('Checkpoint file: %s' % ckpt_file)

                model_dir_exp = os.path.expanduser(self.model_dir)
                saver = tf.compat.v1.train.import_meta_graph(os.path.join(model_dir_exp, meta_file), clear_devices=True)
                tf.compat.v1.get_default_session().run(tf.compat.v1.global_variables_initializer())
                tf.compat.v1.get_default_session().run(tf.compat.v1.local_variables_initializer())
                saver.restore(tf.compat.v1.get_default_session(), os.path.join(model_dir_exp, ckpt_file))
                
                # Retrieve the protobuf graph definition and fix the batch norm nodes
                input_graph_def = sess.graph.as_graph_def()
                
                # Freeze the graph def
                output_graph_def = freeze_graph_def(sess, input_graph_def, 'embeddings,label_batch')

            # Serialize and dump the output graph to the filesystem
            with tf.io.gfile.GFile(sefl.output_file, 'wb') as f:
                f.write(output_graph_def.SerializeToString())
            print("%d ops in the final graph: %s" % (len(output_graph_def.node), self.output_file))
            
    def freeze_graph_def(sess, input_graph_def, output_node_names):
        for node in input_graph_def.node:
            if node.op == 'RefSwitch':
                node.op = 'Switch'
                for index in xrange(len(node.input)):
                    if 'moving_' in node.input[index]:
                        node.input[index] = node.input[index] + '/read'
            elif node.op == 'AssignSub':
                node.op = 'Sub'
                if 'use_locking' in node.attr: del node.attr['use_locking']
            elif node.op == 'AssignAdd':
                node.op = 'Add'
                if 'use_locking' in node.attr: del node.attr['use_locking']
        
        # Get the list of important nodes
        whitelist_names = []
        for node in input_graph_def.node:
            if (node.name.startswith('InceptionResnet') or node.name.startswith('embeddings') or 
                    node.name.startswith('image_batch') or node.name.startswith('label_batch') or
                    node.name.startswith('phase_train') or node.name.startswith('Logits')):
                whitelist_names.append(node.name)

        # Replace all the variables in the graph with constants of the same values
        output_graph_def = graph_util.convert_variables_to_constants(
            sess, input_graph_def, output_node_names.split(","),
            variable_names_whitelist=whitelist_names)
        return output_graph_def