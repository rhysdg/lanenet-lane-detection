#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# @Time    : 18-5-23 上午11:33
# @Author  : MaybeShewill-CV
# @Site    : https://github.com/MaybeShewill-CV/lanenet-lane-detection
# @File    : test_lanenet.py
# @IDE: PyCharm Community Edition
"""
test LaneNet model on single image
"""
import argparse
import os.path as ops
import time
import glob
from tqdm import tqdm

import cv2
import numpy as np
import numpy.ma as ma
import tensorflow as tf

from lanenet_model import lanenet
from lanenet_model import lanenet_postprocess
from local_utils.config_utils import parse_config_utils
from local_utils.log_util import init_logger

CFG = parse_config_utils.lanenet_cfg
LOG = init_logger.get_logger(log_file_name_prefix='lanenet_test')


def init_args():
    """

    :return:
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('--image_path', type=str, help='The image path or the src image save dir')
    parser.add_argument('--weights_path', type=str, help='The model weights path')
    parser.add_argument('--bench', action='store_true')
    parser.add_argument('--display', action='store_true')


    return parser.parse_args()


def args_str2bool(arg_value):
    """

    :param arg_value:
    :return:
    """
    if arg_value.lower() in ('yes', 'true', 't', 'y', '1'):
        return True

    elif arg_value.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Unsupported value encountered.')


def minmax_scale(input_arr):
    """

    :param input_arr:
    :return:
    """
    min_val = np.min(input_arr)
    max_val = np.max(input_arr)

    output_arr = (input_arr - min_val) * 255.0 / (max_val - min_val)

    return output_arr


def test_lanenet(image_path, weights_path, bench=False, display=False):
    """

    :param image_path:
    :param weights_path:
    :return:
    """
    
    #video setup
    save_name = "output.mp4"
    width = 1024
    height = 256
    output_size = (width, height)
    #fps = cap.get(cv2.CAP_PROP_FPS)
    fps = 30
    out = cv2.VideoWriter(save_name,cv2.VideoWriter_fourcc('M','J','P','G'), fps , output_size )




    input_tensor = tf.placeholder(dtype=tf.float32, shape=[1, 256, 512, 3], name='input_tensor')

    net = lanenet.LaneNet(phase='test', cfg=CFG)
    binary_seg_ret, instance_seg_ret = net.inference(input_tensor=input_tensor, name='LaneNet')

    postprocessor = lanenet_postprocess.LaneNetPostProcessor(cfg=CFG)

    # Set sess configuration
    sess_config = tf.ConfigProto()
    sess_config.gpu_options.per_process_gpu_memory_fraction = CFG.GPU.GPU_MEMORY_FRACTION
    sess_config.gpu_options.allow_growth = CFG.GPU.TF_ALLOW_GROWTH
    sess_config.gpu_options.allocator_type = 'BFC'

    sess = tf.Session(config=sess_config)

    # define moving average version of the learned variables for eval
    with tf.variable_scope(name_or_scope='moving_avg'):
        variable_averages = tf.train.ExponentialMovingAverage(
            CFG.SOLVER.MOVING_AVE_DECAY)
        variables_to_restore = variable_averages.variables_to_restore()

    # define saver
    saver = tf.train.Saver(variables_to_restore)
    


    with sess.as_default():
        saver.restore(sess=sess, save_path=weights_path)
        LOG.info('Start reading image and preprocessing')
        
        if args.bench:
            t_start = time.time()
            image = cv2.imread(image_path, cv2.IMREAD_COLOR)
            image_vis = image
            img = cv2.resize(image, (512, 256), interpolation=cv2.INTER_LINEAR)
            image = img / 127.5 - 1.0
            LOG.info('Image load complete, cost time: {:.5f}s'.format(time.time() - t_start))
            
            t_start = time.time()
            loop_times = 500
            for i in range(loop_times):
                binary_seg_image, instance_seg_image = sess.run(
                    [binary_seg_ret, instance_seg_ret],
                    feed_dict={input_tensor: [image]}
                )
            t_cost = time.time() - t_start
            t_cost /= loop_times
            LOG.info('Single imgae inference cost time: {:.5f}s'.format(t_cost))

        for image in tqdm(sorted(glob.glob('/home/rhysdg/data/culane_video/05081544_0305/05081544_0305*.jpg'))):
            image = cv2.imread(image, cv2.IMREAD_COLOR)
            image_vis = image
            img = cv2.resize(image, (512, 256), interpolation=cv2.INTER_LINEAR)
            image = img / 127.5 - 1.0
            
            binary_seg_image, instance_seg_image = sess.run(
                    [binary_seg_ret, instance_seg_ret],
                    feed_dict={input_tensor: [image]}
                )
            postprocess_result = postprocessor.postprocess(
                binary_seg_result=binary_seg_image[0],
                instance_seg_result=instance_seg_image[0],
                source_image=image_vis
            )
            mask_image = postprocess_result['mask_image']

            for i in range(CFG.MODEL.EMBEDDING_FEATS_DIMS):
                instance_seg_image[0][:, :, i] = minmax_scale(instance_seg_image[0][:, :, i])
            embedding_image = np.array(instance_seg_image[0], np.uint8)
            embedding_image = cv2.cvtColor(embedding_image,  cv2.COLOR_BGRA2BGR)

            binary = np.uint8(binary_seg_image[0])
            img_overlay = img.copy()
            img_overlay[binary >0,  0] = 200
            #img[binary >0,  1] = 34
            #img[binary >0,  2] = 34
            
            merged = np.concatenate((img_overlay, embedding_image), axis=1)
            
            cv2.putText(merged, 'Binary', (10, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1, cv2.LINE_AA)
            cv2.putText(merged, 'Instance', (522, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1, cv2.LINE_AA)
            
            out.write(cv2.resize(merged, output_size))    
            if display:
                cv2.imshow('test', merged)
                
            if cv2.waitKey(1) & 0xFF == ord('q'): 
                out.release()#
                break
                
        out.release()
        cv2.destroyAllWindows()


    sess.close()
  
    return

if __name__ == '__main__':
    """
    test code
    """
    # init args
    args = init_args()

    test_lanenet(args.image_path, args.weights_path,  bench=args.bench,  display=args.display)