import itertools
import json
import os
import pickle
import random
import sys
import time
from math import cos, pi, sin, tan
from os import listdir
from os.path import basename, expanduser, isdir, isfile, join

import numpy as np
import plotly.plotly as py  # for sending things to plotly
import plotly.tools as tls  # for mpl, config, etc.
import scipy as sc
import scipy.io as sio
from joblib import Parallel, delayed
from matplotlib import pyplot as plt
from plotly.graph_objs import *
from scipy import weave
from scipy.optimize import linear_sum_assignment
from tqdm import tqdm

from pylsd import lsd
from utils.libs import *
from utils.load_data_funcs import *

home = expanduser("~")
sys.path.insert(0, join(home, 'ws/nk/'))

thresholds_list = [0.01 + 0.01 * i
                   for i in range(9)] + [0.1 + 0.1 * i
                                         for i in range(9)] + [0.91 + 0.01 * i for i in range(9)]
divide_eps = 1e-20


def testYork():
    src_dir = "/home/hk/ws/dataset/YorkUrbanDB/imgs"
    with open(join(src_dir, '../files.txt'), 'r') as fn:
        filelst = fn.read().splitlines()
    data = loadYorkDB(src_dir, filelst)

    for anno in data:
        imgname = anno[0]
        img = anno[1]
        line = anno[2]
        im = addLines(img, line, display_=False, color=(0, 0, 255), rand_color=True, thickness=2)
        sio.savemat(
            join(src_dir, imgname + '.mat'), {
                'imgname': imgname,
                "img": img,
                'line': line
            })
        cv2.imwrite("/var/www/html/york_dataset/%s_line.png" % imgname, im)
        cv2.imwrite("/var/www/html/york_dataset/%s_origin.png" % imgname, img)
    generate_html(filelst, 'york_dataset', table_keys=['origin', 'line'])


def calcAssignment(th1, th2, dist=7.5):
    H = len(th1)
    W = len(th2)
    costMatrix = np.zeros((H, W))
    m1 = np.array(th1, dtype=np.float32)
    m2 = np.array(th2, dtype=np.float32)
    m1 = np.reshape(m1, (H, 1))
    m2 = np.reshape(m2, (1, W))
    costMatrix = np.abs(m1 - m2)
    costMatrix = np.minimum(costMatrix, 360 - costMatrix)
    costMatrix[costMatrix > dist] = 1000.
    ass_i, ass_j = linear_sum_assignment(costMatrix)

    good = []
    bad = []
    residual = 0.
    for i, j in zip(ass_i, ass_j):
        if costMatrix[i, j] <= dist:
            good.append((i, j))
            residual += costMatrix[i, j]
        elif costMatrix[i, j] == 1000.:
            bad.append((i, j))
    return good, bad, residual


def theta_dist(th1, th2):
    d1 = min(th1, th2)
    d2 = max(th1, th2)
    return min(d2 - d1, d1 + 360 - d2)


def deltaTheta(ep, sp, pt):
    if not isinstance(pt, np.ndarray):
        pt = np.array(pt, dtype=np.float32)
    dir_v = np.stack([np.cos(pt), np.sin(pt)], axis=-1)

    ep = ep[:, np.newaxis, :]
    sp = sp[np.newaxis, :, :]
    v = ep - sp

    dir_v = dir_v[np.newaxis, :, :]

    se = np.linalg.norm(v, axis=-1, keepdims=False)
    cosThetas = innerProduct(v, dir_v) / (se + eps)
    cosThetas = np.clip(cosThetas, -1, 1)
    angles = np.arccos(cosThetas)
    angles = angles * 180. / pi
    return angles


def pointDistMatrix(pts1, pts2):
    v = pts1[:, np.newaxis, :] - pts2[np.newaxis, :, :]
    dist = np.linalg.norm(v, axis=2)

    return dist


def saveJunction(exp_id, iteration, dataset_name='test_all'):

    root_dir = join(home, 'ws/ws/zihan/res/')
    with open('samples/%s.txt' % dataset_name, 'r') as f:
        imgnames = f.read().splitlines()

    use_mp = False
    H = {}

    src_dir = join(home, 'ws/dataset/v1.1_pl/') if dataset_name == 'test_all' else join(
        home, 'ws/dataset/junc_bench/BSDS500/test')
    files = [x[:-4] if x.endswith('.jpg') else x for x in imgnames]
    gts = loadNewGt(src_dir, files)

    save_root_dir = 'result'

    for th in [0, 1, 2, 3, 4, 5, 6, 7, 8]:
        save_dir = "%s/%s/%s/%s/%s" % (save_root_dir, exp_id, iteration, th, dataset_name)
        html_dir = "%s/%s/%s/%s/%s" % (save_root_dir, exp_id, iteration, th, dataset_name)

        generate_html(files, html_dir, table_keys=['g', 'p'])

        if not isdir(save_dir):
            os.makedirs(save_dir)
        if not isdir(html_dir):
            os.makedirs(html_dir)

        H['paths'] = (root_dir, src_dir, save_dir, html_dir)
        # if theta is not thresholded, set theta_thresh
        preds = loadRawPrediction(files, root_dir, exp_id, iteration, th, phase=dataset_name)

        if use_mp:
            Parallel(n_jobs=25)(delayed(save_single_image)(in_, preds[in_], gts[in_], img_idx, H)
                                for img_idx, in_ in enumerate(files))
        else:
            for img_idx, in_ in enumerate(tqdm(files)):
                save_single_image(in_, preds[in_], gts[in_], img_idx, H)


def save_single_image(in_, pred, gt, img_idx, H):

    print("{} {}".format(img_idx, in_))

    (root_dir, src_dir, save_dir, html_dir) = H['paths']

    DEBUG = False

    img = cv2.imread(join(src_dir, in_ + '.jpg'))
    _, gt_junctions, gt_thetas, gt_points, gt_lines = gt
    data = {}
    data['label'] = gt_junctions
    #sio.savemat("%s/%s_g.mat"%(save_dir, in_), data)

    if DEBUG:
        print(len(gt_junctions), len(gt_thetas), img.shape)

    newim = showJunctionPrediction(img, gt_junctions, gt_thetas, display_=True
                                   if DEBUG else False, thickness=2, color=(0, 255, 200))
    cv2.imwrite(join(html_dir, in_ + '_g.png'), newim)

    _, pred_junctions, pred_thetas, _ = pred

    #thetas = [thresholding(ths, ths_confs, theta_thresh)[0] for ths, ths_confs in zip(pred_thetas, theta_confs)]
    #junctions, nthetas = removeDupJunctions(pred_junctions, pred_thetas)
    #nthetas = removeDupTheta(nthetas)
    if DEBUG:
        for xy in pred_junctions:
            print(xy)
        for th in pred_thetas:
            print(th)

    newim = showJunctionPrediction(img, pred_junctions, pred_thetas, display_=True if DEBUG else
                                   False, thickness=2, color=(0, 255, 200), rand_color=False)
    cv2.imwrite(join(html_dir, in_ + '_p.png'), newim)

    #assert len(junctions) == len(nthetas)

    h, w = img.shape[:2]
    tmp = {}
    tmp['h'] = h
    tmp['w'] = w
    tmp['junctions'] = pred_junctions
    tmp['thetas'] = pred_thetas
    sio.savemat("%s/%s_p.mat" % (save_dir, in_), tmp)


def proposeLines(exp_id, iteration):
    dataset_name = 'test_all'
    #dataset_name = 'york'

    with open('samples/%s.txt' % dataset_name, 'r') as f:
        imgnames = f.read().splitlines()

    H = {}

    root_dir = join(home, 'ws/ws/zihan/res/')
    src_dir = join(home, 'ws/dataset/v1.1_pl/')
    if dataset_name == 'york':
        src_dir = join(home, 'ws/dataset/YorkUrbanDB/imgs')

    line_folder = 'york' if dataset_name == 'york' else '3'
    H['line_folder'] = line_folder

    load_mcmlsd = True
    load_lsd = True
    save_gt_junctions = True
    save_pred = True
    save_line_pred = True
    save_line_gt = True
    save_junction_pred = True

    #line_thresholds  = [0, 5] + [10 * t + 10 for t in range(25)] + [255]

    line_thresholds = [50]

    #imgnames = ['00031811.jpg', '00076835.jpg', '00075041.jpg', '00036977.jpg', "00059148.jpg", "00031608.jpg", "00071079.jpg"]
    #imgnames = ["00059148.jpg"]
    #imgnames = ['00031546.jpg']
    #imgnames = ['00110830.jpg']
    #imgnames = ['00031811.jpg']

    use_mp = False

    files = [x[:-4] if x.endswith('.jpg') else x for x in imgnames]
    if dataset_name != 'york':
        gts = loadNewGt(src_dir, files)

    preds = loadRawPrediction(files, root_dir, exp_id, iteration, 1, phase=dataset_name)

    lsd_save_dir = "result/lsd/"
    files = files[:100]
    for lth_idx, lth in enumerate(line_thresholds):
        #save_dir = "/var/www/html/%s_%s_%s/%s"%(dataset_name, exp_id, iteration, lth)
        #line_save_dir = "/var/www/html/%s_%s_%s_lines/%s"%(dataset_name, exp_id, iteration, lth)

        save_dir = "result/%s_%s_%s/%s" % (dataset_name, exp_id, iteration, lth)
        line_save_dir = "result/%s_%s_%s_lines/%s" % (dataset_name, exp_id, iteration, lth)

        if not isdir(save_dir):
            os.makedirs(save_dir)
        if not isdir(line_save_dir):
            os.makedirs(line_save_dir)

        H['paths'] = (root_dir, src_dir, save_dir, line_save_dir, lsd_save_dir)
        H['line_thresh'] = lth
        # generate_html([x[:-4] for x in imgnames], "result/%s_%s_%s/%s"%(dataset_name, exp_id, iteration, lth),
        #          table_keys=[
        #                      'gt_lines',
        #                      'pred_lines',
        #                      'gt',
        #                      'map_t',
        #                      'pred',
        #                      't22_1',
        #                      't22_2',
        #                      't22_3',
        #                      't22_4',
        #                      'mcmlsd',
        #          ])

        if use_mp:
            Parallel(n_jobs=25)(delayed(propose_single_image)(in_, preds[
                in_], img_idx, H, gt=None if dataset_name == 'york' else gts[in_])
                                for img_idx, in_ in enumerate(files))
        else:
            start_time = time.time()
            for img_idx, in_ in enumerate(files):
                propose_single_image(in_, preds[in_], img_idx, H, gt=None
                                     if dataset_name == 'york' else gts[in_])
            end_time = time.time()
            print("num of files: ", len(files), " average time ",
                  (end_time - start_time) / float(len(files)))
            raise


def propose_single_image(in_, pred, img_idx, H, gt=None):
    print("{} {}".format(img_idx, in_))
    phase = H.get('phase', 'final')

    load_mcmlsd = False
    load_lsd = False
    save_gt = False

    save_pred = False
    save_line_pred = False
    save_junction_pred = False

    theta_thresh = 0.25
    dist_eps1, dist_eps2 = 8., 4.

    add_t22_2, add_t22_3, add_t22_4, add_t22_5 = (False, False, True, False)
    save_t22_1, save_t22_2, save_t22_3, save_t22_4, save_t22_5 = (False, False, False, False,
                                                                  False)

    (root_dir, src_dir, save_dir, line_save_dir, lsd_save_dir) = H['paths']
    line_folder = H['line_folder']
    line_thresh = H['line_thresh']

    DEBUG = False
    img = cv2.imread(join(src_dir, in_ + '.jpg'))

    if load_lsd:
        gray_img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        lsd_lines = lsd(gray_img)
        newim = addLines(img, lsd_lines[:, :4], display_=False, rand_color=True, color=(0, 255, 0),
                         thickness=2)
        cv2.imwrite(join(lsd_save_dir, in_ + '_lsd.png'), newim)
        np.save(join(lsd_save_dir, in_ + '_lsd.npy'), np.array(lsd_lines))

    if save_gt:
        _, gt_junctions, gt_thetas, gt_points, gt_lines = gt
        if DEBUG:
            print(len(gt_junctions), len(gt_thetas), img.shape)
        newim = showJunctionPrediction(img, gt_junctions, gt_thetas, display_=False, thickness=2,
                                       color=(0, 255, 200))
        cv2.imwrite(join(save_dir, in_ + '_gt.png'), newim)

        gt_points = np.array(gt_points, dtype=np.float32)
        gt_lines = np.array(gt_lines, dtype=np.float32)
        cv2.imwrite(
            join(save_dir, in_ + '_gt_lines.png'),
            addLines(img, gt_lines, display_=False, rand_color=True, thickness=2, color=(0, 0,
                                                                                         255)))

    _, pred_junctions, pred_thetas, theta_confs = pred
    thetas = [
        thresholding(ths, ths_confs, theta_thresh)[0]
        for ths, ths_confs in zip(pred_thetas, theta_confs)
    ]

    junctions, nthetas = removeDupJunctions(pred_junctions, thetas)
    nthetas = removeDupTheta(nthetas)

    if save_junction_pred:
        cv2.imwrite(
            join(save_dir, in_ + '_pred.png'),
            showJunctionPrediction(img, junctions, nthetas, theta_thresh=theta_thresh,
                                   display_=False, one_by_one=False, thickness=2, rand_color=False,
                                   color=(255, 200, 0)))

    h, w = img.shape[:2]
    max_side_length = max(h, w)

    if DEBUG:
        print("max side lengths: ", max_side_length)

    if load_mcmlsd:
        data = sio.loadmat('mcmlsd/test/%s.mat' % in_)
        mcmlsd_lines = data['lines']
        if DEBUG:
            print("mcmlsd lines: ", mcmlsd_lines.shape)
        if mcmlsd_lines.shape[0] > 0:
            mcmlsd_lines = mcmlsd_lines[:, :4]

            newim = addLines(img, mcmlsd_lines, display_=False, rand_color=True, color=(0, 255, 0),
                             thickness=2)
            cv2.imwrite(join(save_dir, in_ + '_mcmlsd.png'), newim)
        else:
            cv2.imwrite(join(save_dir, in_ + '_mcmlsd.png'), img)

    junctions = np.array(junctions, dtype=np.float32)
    scale_ = np.array((w / 256., h / 256., w / 256., h / 256.), dtype=np.float32)

    lineMap = cv2.imread("%s/%s.png" % (line_folder, in_), 0)
    thresh_map = cv2.threshold(lineMap, line_thresh, 255, cv2.THRESH_BINARY)[1]
    line_pred = cv2.HoughLinesP(thresh_map, 1.8, np.pi / 180, 50)

    if line_pred is not None:
        line_pred = line_pred[:, 0, :]

        #line_pred =  np.load("%s/%s.npy"%(line_folder, in_))
        line_pred = line_pred.reshape((-1, 4))
        line_pred = line_pred * scale_
        line_pred_length = np.linalg.norm(line_pred[:, :2] - line_pred[:, 2:4], axis=1)
        length_above_thresh = np.nonzero(line_pred_length >= 10)[0]
        line_pred = line_pred[length_above_thresh, :]

    m3 = cv2.resize(lineMap, (w, h), cv2.INTER_NEAREST)
    #cv2.imwrite( join(save_dir, in_ + '_map.png'), lineMap)
    m3 = cv2.threshold(m3, line_thresh, 255, cv2.THRESH_BINARY)[1]
    #cv2.imwrite( join(save_dir, in_ + '_map_t.png'), m3)

    DEBUG = False

    if DEBUG:
        showIm(img=lineMap, name='test')

    if save_line_pred:
        cv2.imwrite(
            join(save_dir, in_ + '_pred_lines.png'),
            addLines(img, line_pred, display_=False, rand_color=True, thickness=2,
                     color=(0, 0, 255) if line_pred is not None else img))

    M1 = junctions.shape[0]
    if line_pred is not None:
        point_2 = line_pred.reshape((-1, 2, 2))
        N1 = line_pred.shape[0]
        point_2_1 = point_2[:, 0, :]
        point_2_2 = point_2[:, 1, :]
        M2 = N1
    else:
        M2 = 0

    # Part-12, Part-22 ------------------------------------------------------------------------------------------------
    # in line_2, x1, y1, x2, y2 result from theta. (x1, y1) in on the positive direction of theta

    line_2, line_2_theta = possible_lines((h, w), junctions, nthetas, img=img, DEBUG=False)

    #dev_thetas = [[] for _ in nthetas]
    #dev_thetas_indexes = [[] for _ in nthetas]
    # for t0, th in enumerate(nthetas):
    #    for t1, t in enumerate(th):
    #        dev_thetas[t0].append(t - 2)
    #        dev_thetas[t0].append(t - 1)
    #        dev_thetas[t0].append(t + 1)
    #        dev_thetas[t0].append(t + 2)
    #        dev_thetas_indexes[t0].append(t1)
    #        dev_thetas_indexes[t0].append(t1)
    #        dev_thetas_indexes[t0].append(t1)
    #        dev_thetas_indexes[t0].append(t1)

    #line_2_devi, line_2_theta_devi = possible_lines((h, w), junctions, dev_thetas, img=img, DEBUG=False)

    im = img
    Nj = junctions.shape[0]
    DEBUG = False

    # calculate d_min of junction and line_2
    line_2_mix = []
    line_2_theta_mix = []
    line_2_map_junction = []
    line_2_map_indexes = [[] for _ in junctions]
    for idx, p in enumerate(junctions):
        line_2_p = [(x, y, p[0], p[1]) for x, y, _, _ in line_2[idx]]
        for l, t in zip(line_2_p, line_2_theta[idx]):
            line_2_mix.append(l)
            line_2_theta_mix.append(t)
            line_2_map_junction.append(idx)
            line_2_map_indexes[idx].append(len(line_2_mix) - 1)
    line_2_mix = np.array(line_2_mix, dtype=np.float32)

    perp_points_12, dist_12, within_line_12, theta_12 = calc_dist_theta(junctions, line_2_mix)

    N2 = line_2_mix.shape[0]

    T12 = np.zeros((N2, M1))
    T12 -= 1
    within_T12 = np.zeros(T12.shape).astype(np.float32)
    within_T12 -= 1.

    for i in range(N2):
        point_idx = line_2_map_junction[i]
        for j in range(M1):
            if point_idx == j:
                continue
            on_line = within_line_12[j, i, 2]
            delta_t = theta_12[j, i]
            dist = dist_12[j, i, 0]
            dist_to_junction = dist_12[j, i, 3]

            # if dist < 2.5 or delta_t < 2.5:
            if delta_t < 1.6 or (dist <= 4.5 and dist_to_junction < 130):
                T12[i, j] = delta_t
                if on_line:
                    within_T12[i, j] = delta_t

    mutual_T12 = -np.ones(T12.shape)
    back_T12 = -np.ones(T12.shape)

    # N2 x M1
    DEBUG = False

    for i in range(N2):
        mapped_point_idx = line_2_map_junction[i]
        indexes = np.nonzero(within_T12[i, :] > -1)[0]

        im = img
        im = addLines(im, line_2_mix[i:i + 1], display_=False, rand_color=False, color=(0, 255, 0),
                      thickness=2)
        im = addPoints(im, junctions[mapped_point_idx:mapped_point_idx + 1], display_=False,
                       thickness=3, color=(0, 0, 150))

        if len(indexes) == 0:
            #im = addLines(im, line_2_mix[i:i+1], display_ = False, rand_color=True, color=(255, 0, 0), thickness=1)
            continue
        thetas_to_print = []

        for idx in indexes:
            if idx == mapped_point_idx:
                continue
            subset_indexes = line_2_map_indexes[idx]
            #np.nonzero(lines_map_matrix == idx)[0]

            for si in subset_indexes:
                if within_T12[si, mapped_point_idx] > -1:
                    mutual_T12[i, idx] = si
                    #im = addLines(im, line_2_mix[si:si+1], display_ = False, rand_color=False, color=(0, 0, 255), thickness=1)
                    thetas_to_print.append((within_T12[i, idx], within_T12[si, mapped_point_idx]))
                    break
                elif T12[si, mapped_point_idx] > -1:
                    back_T12[i, idx] = si
                    im = addLines(im, line_2_mix[si:si + 1], display_=False, rand_color=True,
                                  color=(0, 0, 255), thickness=2)
                    thetas_to_print.append((within_T12[i, idx], within_T12[si, mapped_point_idx]))

        if DEBUG:
            showIm(img=im, name="checking connection")

    mutual_T12 = mutual_T12.astype(np.int32)

    DEBUG = False
    lines_1 = []
    im = img

    line2Line = np.zeros((N2, N2)).astype(np.int32)

    for i in range(N2):
        k = line_2_map_junction[i]
        im = addPoints(im, junctions[k:k + 1], display_=False, thickness=2, color=(0, 0, 0))
        point_indexes = np.nonzero(mutual_T12[i, :] > -1)[0]
        #im = addPoints(im, junctions[point_indexes], display_=False, thickness=2, color=(255, 128, 7))

        x1, y1, x2, y2 = line_2_mix[i].tolist()

        if len(point_indexes) > 0:
            lengths = [(k, dist_12[k, i, 3]) for k in point_indexes]
            lengths.sort(key=lambda x: x[1])
            endpoint_idx = lengths[0][0]

            line_idx = mutual_T12[i, endpoint_idx]
            line2Line[i, line_idx] = 1
            line2Line[line_idx, i] = 1

    lineDistMatrix = pointDistMatrix(junctions[line_2_map_junction, :],
                                     junctions[line_2_map_junction, :])
    for i in range(N2):
        nonzero_indexes = np.nonzero(line2Line[i, :] > 0)[0]
        if len(nonzero_indexes) > 1:
            dists = lineDistMatrix[i, nonzero_indexes]
            smallest_indexes = dists.argmin()
            for k, n_idx in enumerate(nonzero_indexes):
                if k != smallest_indexes:
                    line2Line[i, n_idx] = 0
                    line2Line[n_idx, i] = 0

    for i in range(N2):
        nonzero_indexes = np.nonzero(line2Line[i, :] > 0)[0]
        assert len(nonzero_indexes) <= 1, len(nonzero_indexes)
        if len(nonzero_indexes) == 1:
            ni = nonzero_indexes[0]
            x1, y1, x2, y2 = (line_2_mix[ni, 2], line_2_mix[ni, 3], line_2_mix[i, 2],
                              line_2_mix[i, 3])
            length_ = sqrt((x1 - x2)**2 + (y1 - y2)**2)
            adding_line = False
            if length_ < max_side_length / 2.0:
                adding_line = True
            else:
                #coords = linespace((x1, y1), (x2, y2), img.shape[:2])
                if DEBUG:
                    print(coords)
                ratio, max_loc, _ = pixelRatio((x1, y1), (x2, y2), m3)
                if ratio > 0.6:
                    adding_line = True

            if adding_line:
                im = addLines(im, [(x1, y1, x2, y2)], display_=False, rand_color=True,
                              color=(0, 255, 0), thickness=2)
                lines_1.append((line_2_mix[ni, 2], line_2_mix[ni, 3], line_2_mix[i, 2],
                                line_2_mix[i, 3]))

    if save_t22_1:
        res_1 = addLines(img, lines_1, display_=False, rand_color=False, color=(0, 255, 0),
                         thickness=2)
        res_1 = addPoints(res_1, junctions, display_=False, thickness=3, color=(0, 0, 255))
        cv2.imwrite(join(save_dir, in_ + '_t22_1.png'), res_1)
        np.save(join(line_save_dir, in_ + '_line_1.npy'), np.array(lines_1))

    lines_2 = []

    if line_pred is None:
        add_t22_2 = False

    if add_t22_2:
        im_2 = np.copy(im)
        DEBUG = False

        for i in range(N2):
            im_tmp = np.copy(im_2)

            k = line_2_map_junction[i]
            im = addPoints(im, junctions[k:k + 1], display_=False, thickness=2, color=(0, 0, 0))
            px, py = junctions[k]
            bi_point_indexes = np.nonzero(mutual_T12[i, :] > -1)[0]
            single_point_indexes = np.nonzero(back_T12[i, :] > -1)[0]

            intervals = []
            if DEBUG:
                print("line ", i)

            if len(bi_point_indexes) == 0:
                # and len(single_point_indexes) == 0:
                im_tmp = addLines(im_tmp, line_2_mix[i:i + 1], display_=False, rand_color=False,
                                  color=(0, 255, 0), thickness=2)
                if DEBUG:
                    showIm(img=im_tmp, name='Line i')

                # purely depends on line segment support.
                for j in range(M2):
                    if T22[i, j, 0] == 1 and T22[i, j, 1] == 1:
                        angle = angle_of_lines[i, j]
                        d1 = dist_22_1[j, i, 3]
                        d2 = dist_22_2[j, i, 3]

                        if angle < 6. and max(d1, d2) > 0:
                            start = max(0, min(d1, d2))
                            end = max(d1, d2)
                            max_idx = 1 if d1 < d2 else 0

                            if start < 30.:
                                intervals.append(((start, end), angle, j, max_idx))
                            if DEBUG:
                                print("   interval {} angle {} ends {}, {}, {}, {}".format(
                                    j, angle, start, end, d1, d2))
                            im_tmp = addLines(im_tmp, line_pred[j:j + 1], display_=False,
                                              rand_color=True, color=(0, 255, 0), thickness=2)
                            if DEBUG:
                                showIm(img=im_tmp, name='Line i')

                if len(intervals) > 0:
                    intervals.sort(key=lambda x: x[1])
                    if DEBUG:
                        print("sorted intervals: ", intervals)

                    length_intervals = []
                    for idx, int_ in enumerate(intervals):
                        if int_[1] < 2.5:
                            length_intervals.append(int_)
                    if DEBUG:
                        print("length_intervals: ", len(length_intervals))

                    if len(length_intervals) > 0:
                        length_intervals.sort(key=lambda x: x[0][1])
                        p_idx = length_intervals[-1][2]
                        max_idx = length_intervals[-1][3]
                        start, end = length_intervals[-1][0]
                    else:
                        p_idx = intervals[0][2]
                        max_idx = intervals[0][3]
                        start, end = intervals[0][0]

                    point = point_2_1[p_idx, :] if max_idx == 0 else point_2_2[p_idx, :]
                    #line = (line_2_mix[i, 2], line_2_mix[i, 3], point[0], point[1])
                    tx, ty, kx, ky = line_pred[p_idx, [0, 1, 2, 3]] if max_idx == 0 else line_pred[
                        p_idx, [2, 3, 0, 1]]
                    dxy = sqrt((tx - kx)**2 + (ty - ky)**2)
                    cx, cy = (tx - kx) / (dxy + eps), (ty - ky) / (dxy + eps)
                    ppx, ppy = px + cx * end, py + cy * end
                    #ppx, ppy = tx - kx + px, ty - ky + py
                    line_to_append = (px, py, ppx, ppy)
                    lines_2.append(line_to_append)
                    im_2 = addLines(im_2, [line_to_append], display_=False, rand_color=False,
                                    color=(0, 255, 0), thickness=2)
        if save_t22_2:
            res_2 = addLines(res_1, lines_2, display_=False, rand_color=False, color=(0, 255, 0)
                             if phase == 'final' else (0, 255, 255), thickness=2)
            cv2.imwrite(join(save_dir, in_ + '_t22_2.png'), res_2)
            np.save(join(line_save_dir, in_ + '_line_2.npy'), np.array(lines_1 + lines_2))

    # With no hough transform
    ###################################### t22_3 #######################################

    lines_3 = []

    if add_t22_3:
        im_3 = np.copy(im)
        DEBUG = False

        # if DEBUG:
        #    showIm(img=im_3, name='Line 3')

        for i in range(N2):
            if DEBUG:
                print("\n-------------------------------------------------------- \n line", i)
            im_x = img

            #bi_point_indexes = np.nonzero(line2Line[i, :] > 0)[0]
            bi_point_indexes = np.nonzero(mutual_T12[i, :] > -1)[0]
            single_point_indexes = np.nonzero(back_T12[i, :] > -1)[0]
            online_point_indexes = np.nonzero(within_T12[i, :] > -1)[0]

            bx, by = line_2_mix[i, 0], line_2_mix[i, 1]
            px, py = line_2_mix[i, 2], line_2_mix[i, 3]
            k = line_2_map_junction[i]

            if len(bi_point_indexes) == 0 and len(online_point_indexes) == 0:
                im_x = addPoints(im_x, junctions[k:k + 1], display_=False, thickness=3,
                                 color=(255, 0, 0))
                im_x = addLines(im_x, line_2_mix[i:i + 1], display_=False, rand_color=False,
                                color=(0, 255, 0), thickness=2)

                ratio, max_loc, _ = pixelRatio((px, py), (bx, by), m3)
                if ratio < 0.05:
                    continue

                bx, by = max_loc
                intersects = intersections(
                    np.array([px, py, bx, by], dtype=np.float32),
                    np.array(lines_1, dtype=np.float32))
                if DEBUG:
                    im_3 = addPoints(im_3, intersects, display_=False, thickness=3, color=(0, 0,
                                                                                           255))
                im_x = addPoints(im_x, intersects, display_=False, thickness=3, color=(0, 0, 255))

                if DEBUG:
                    print("Intersects.", len(intersects))

                start_list = [(px, py)]
                end_list = []

                for int_ in intersects:
                    start_list.append(int_)
                    end_list.append(int_)
                end_list.append((bx, by))

                valid_interval_idx = []

                next_start = None
                previous_end = None

                for idx, (start, end) in enumerate(zip(start_list, end_list)):
                    if next_start is None:
                        next_start = start

                    line_ratio, max_pos_idx, max_pos_loc = pixelRatio(start, end, m3)
                    if DEBUG:
                        print("       distance of start, end ", distance(start, end), " ratio: ",
                              line_ratio)
                    adding_line = False

                    valid_cond = line_ratio > 0.6 and max_pos_loc > 0.75
                    if idx == 0:
                        if distance(start, end) < max_side_length / 20. or valid_cond:
                            adding_line = True
                    elif valid_cond:
                        adding_line = True

                    if adding_line:
                        # if DEBUG:
                        #    print "distance of start, end ", distance(start, end), " ratio: ", line_ratio
                        previous_end = end
                        im_x = addLines(im_x, [(start[0], start[1], end[0], end[1])],
                                        display_=False, rand_color=False, color=(255, 0,
                                                                                 255), thickness=2)
                        im_3 = addLines(im_3, [(start[0], start[1], end[0], end[1])],
                                        display_=False, rand_color=False, color=(40, 255,
                                                                                 0), thickness=2)
                        lines_3.append((start[0], start[1], end[0], end[1]))
                        if DEBUG:
                            showIm(img=im_x, name='Line i')
                            showIm(img=im_3, name='Line 3')
                    else:
                        # if previous_end is not None:
                        #    lines_3.append((next_start[0], next_start[1], previous_end[0], previous_end[1]))

                        next_start = None
                        previous_end = None

            elif len(bi_point_indexes) == 0 and len(online_point_indexes) > 0:
                im_x = addPoints(im_x, junctions[k:k + 1], display_=False, thickness=3,
                                 color=(255, 0, 0))
                im_x = addLines(im_x, line_2_mix[i:i + 1], display_=False, rand_color=False,
                                color=(0, 255, 0), thickness=2)

                #perps = [perp_points_12[p_idx, i] for p_idx in online_point_indexes]

                im_x = addPoints(im_x, junctions[online_point_indexes], display_=False,
                                 thickness=3, color=(0, 0, 255))
                online_point_indexes = online_point_indexes.tolist()
                online_point_indexes.sort(key=lambda x: distance(perp_points_12[x, i], (px, py)))

                ratio, max_loc, _ = pixelRatio((px, py), (bx, by), m3)
                if ratio < 0.05:
                    continue
                bx, by = max_loc

                start_list = [(px, py)]
                end_list = []

                if DEBUG:
                    print("online points: ", len(online_point_indexes))

                for on_idx in online_point_indexes:
                    start_list.append(perp_points_12[on_idx, i])
                    end_list.append(perp_points_12[on_idx, i])
                end_list.append((bx, by))

                next_start = None
                previous_end = None
                for idx, (start, end) in enumerate(zip(start_list, end_list)):
                    if next_start is None:
                        next_start = start

                    line_ratio, max_pos_idx, max_pos_loc = pixelRatio(start, end, m3)
                    if DEBUG:
                        print("       distance of start, end ", distance(start, end), " ratio: ",
                              line_ratio)
                    adding_line = False

                    valid_cond = line_ratio > 0.6 and max_pos_loc > 0.75

                    if idx == 0:
                        if distance(start, end) < max_side_length / 20. or valid_cond:
                            #lines_3.append((start[0], start[1], end[0], end[1]))
                            adding_line = True
                    elif valid_cond:
                        #lines_3.append((start[0], start[1], end[0], end[1]))
                        adding_line = True

                    if adding_line:
                        previous_end = end
                        # if DEBUG:
                        #    print "distance of start, end ", distance(start, end), " ratio: ", line_ratio

                        im_x = addLines(im_x, [(start[0], start[1], end[0], end[1])],
                                        display_=False, rand_color=False, color=(255, 0,
                                                                                 255), thickness=2)
                        im_3 = addLines(im_3, [(start[0], start[1], end[0], end[1])],
                                        display_=False, rand_color=False, color=(40, 255,
                                                                                 0), thickness=2)
                        lines_3.append((start[0], start[1], end[0], end[1]))
                        if DEBUG:
                            showIm(img=im_x, name='Line i')
                            showIm(img=im_3, name='Line 3')
                    else:
                        # if previous_end is not None:
                        #    lines_3.append((next_start[0], next_start[1], previous_end[0], previous_end[1]))

                        next_start = None
                        previous_end = None

                if DEBUG:
                    showIm(img=im_x, name='Line i')
        if save_t22_3:
            print("lines_3: ", len(lines_3))
            res_3 = addLines(res_1, lines_3, display_=False, rand_color=False, color=(0, 255, 0)
                             if phase == 'final' else (255, 255, 0), thickness=2)
            cv2.imwrite(join(save_dir, in_ + '_t22_3.png'), res_3)
            np.save(join(line_save_dir, in_ + '_line_3.npy'), np.array(lines_1 + lines_3))

    # Modify t22_3:
    # for all the cuts, only take the first.
    ###################################### t22_4 #######################################
    lines_4 = []
    im_4 = img
    if add_t22_4:
        #im_4= np.copy(res_1)
        DEBUG = False
        for i in range(N2):
            if DEBUG:
                print("\n-------------------------------------------------------- \n line", i)
            im_x = img

            #bi_point_indexes = np.nonzero(line2Line[i, :] > 0)[0]
            bi_point_indexes = np.nonzero(mutual_T12[i, :] > -1)[0]
            single_point_indexes = np.nonzero(back_T12[i, :] > -1)[0]
            online_point_indexes = np.nonzero(within_T12[i, :] > -1)[0]

            bx, by = line_2_mix[i, 0], line_2_mix[i, 1]
            px, py = line_2_mix[i, 2], line_2_mix[i, 3]
            k = line_2_map_junction[i]

            if distance((px, py), (bx, by)) < 0.05 * max_side_length:
                lines_4.append((px, py, bx, by))
                #im_4 = addLines(im_4, [(px, py, bx, by)], display_ = False, rand_color=False, color=(40, 255, 0), thickness=2)
                if DEBUG:
                    showIm(img=im_x, name='Line i')
                    showIm(img=im_4, name='Line 3')
                continue

            if len(bi_point_indexes) == 0 and len(online_point_indexes) == 0:
                im_x = addPoints(im_x, junctions[k:k + 1], display_=False, thickness=3,
                                 color=(255, 0, 0))
                im_x = addLines(im_x, line_2_mix[i:i + 1], display_=False, rand_color=False,
                                color=(0, 255, 0), thickness=2)

                ratio, max_loc, _ = pixelRatio((px, py), (bx, by), m3)
                if ratio < 0.05:
                    continue

                bx, by = max_loc

                intersects = intersections(
                    np.array([px, py, bx, by], dtype=np.float32),
                    np.array(lines_1, dtype=np.float32))
                if DEBUG:
                    im_4 = addPoints(im_4, intersects, display_=False, thickness=3, color=(0, 0,
                                                                                           255))
                im_x = addPoints(im_x, intersects, display_=False, thickness=3, color=(0, 0, 255))

                if DEBUG:
                    print("Intersects.", len(intersects))

                start_list = [(px, py)]
                end_list = []

                for int_ in intersects:
                    start_list.append(int_)
                    end_list.append(int_)
                end_list.append((bx, by))

                valid_interval_idx = []

                next_start = None
                previous_end = None

                first_flag = True
                for idx, (start, end) in enumerate(zip(start_list, end_list)):
                    if not first_flag:
                        break

                    if next_start is None:
                        next_start = start

                    line_ratio, max_pos_idx, max_pos_loc = pixelRatio(start, end, m3)
                    if DEBUG:
                        print("       distance of start, end ", distance(start, end), " ratio: ",
                              line_ratio)
                    adding_line = False

                    valid_cond = line_ratio > 0.6 and max_pos_loc > 0.75
                    if idx == 0:
                        if distance(start, end) < max_side_length / 20. or valid_cond:
                            adding_line = True
                    elif valid_cond:
                        adding_line = True

                    if adding_line:
                        # if DEBUG:
                        #    print "distance of start, end ", distance(start, end), " ratio: ", line_ratio
                        previous_end = end
                        im_x = addLines(im_x, [(start[0], start[1], end[0], end[1])],
                                        display_=False, rand_color=False, color=(255, 0,
                                                                                 255), thickness=2)
                        #im_4 = addLines(im_4, [(start[0], start[1], end[0], end[1])], display_ = False, rand_color=False, color=(40, 255, 0), thickness=2)
                        lines_4.append((start[0], start[1], end[0], end[1]))

                        if DEBUG:
                            showIm(img=im_x, name='Line i')
                        #    showIm(img=im_4, name='Line 3')
                    else:
                        # if previous_end is not None:
                        #    lines_3.append((next_start[0], next_start[1], previous_end[0], previous_end[1]))
                        if idx == 0:
                            first_flag = False
                        next_start = None
                        previous_end = None

            elif len(bi_point_indexes) == 0 and len(online_point_indexes) > 0:
                im_x = addPoints(im_x, junctions[k:k + 1], display_=False, thickness=3,
                                 color=(255, 0, 0))
                im_x = addLines(im_x, line_2_mix[i:i + 1], display_=False, rand_color=False,
                                color=(0, 255, 0), thickness=2)

                #perps = [perp_points_12[p_idx, i] for p_idx in online_point_indexes]

                im_x = addPoints(im_x, junctions[online_point_indexes], display_=False,
                                 thickness=3, color=(0, 0, 255))
                online_point_indexes = online_point_indexes.tolist()
                online_point_indexes.sort(key=lambda x: distance(perp_points_12[x, i], (px, py)))

                ratio, max_loc, _ = pixelRatio((px, py), (bx, by), m3)
                if ratio < 0.05:
                    continue
                bx, by = max_loc

                start_list = [(px, py)]
                end_list = []

                if DEBUG:
                    print("online points: ", len(online_point_indexes))

                for on_idx in online_point_indexes:
                    start_list.append(perp_points_12[on_idx, i])
                    end_list.append(perp_points_12[on_idx, i])
                end_list.append((bx, by))

                next_start = None
                previous_end = None
                for idx, (start, end) in enumerate(zip(start_list, end_list)):
                    if next_start is None:
                        next_start = start

                    line_ratio, max_pos_idx, max_pos_loc = pixelRatio(start, end, m3)
                    if DEBUG:
                        print("       distance of start, end ", distance(start, end), " ratio: ",
                              line_ratio)
                    adding_line = False

                    valid_cond = line_ratio > 0.6 and max_pos_loc > 0.75

                    if idx == 0:
                        if distance(start, end) < max_side_length / 20. or valid_cond:
                            #lines_3.append((start[0], start[1], end[0], end[1]))
                            adding_line = True
                    elif valid_cond:
                        #lines_3.append((start[0], start[1], end[0], end[1]))
                        adding_line = True

                    if adding_line:
                        previous_end = end
                        # if DEBUG:
                        #    print "distance of start, end ", distance(start, end), " ratio: ", line_ratio

                        im_x = addLines(im_x, [(start[0], start[1], end[0], end[1])],
                                        display_=False, rand_color=False, color=(255, 0,
                                                                                 255), thickness=2)
                        #im_4 = addLines(im_4, [(start[0], start[1], end[0], end[1])], display_ = False, rand_color=False, color=(40, 255, 0), thickness=2)
                        lines_4.append((start[0], start[1], end[0], end[1]))
                        if DEBUG:
                            showIm(img=im_x, name='Line i')
                            #showIm(img=im_4, name='Line 3')
                    else:
                        # if previous_end is not None:
                        #    lines_3.append((next_start[0], next_start[1], previous_end[0], previous_end[1]))

                        next_start = None
                        previous_end = None

                if DEBUG:
                    showIm(img=im_x, name='Line i')

        if save_t22_4:
            print("lines_4: ", len(lines_4))
            res_4 = addLines(res_1, lines_4, display_=False, rand_color=False, color=(0, 255, 0)
                             if phase == 'final' else (0, 0, 125), thickness=2)
            cv2.imwrite(join(save_dir, in_ + '_t22_4.png'), res_4)
            np.save(join(line_save_dir, in_ + '_line_4.npy'), np.array(lines_1 + lines_4))

    # Modify t22_3:
    # for all the cuts, only take the first.
    ###################################### t22_4 #######################################
    lines_5 = []

    if add_t22_5:
        im_5 = np.copy(res_1)
        DEBUG = False
        for i in range(N2):
            if DEBUG:
                print("\n-------------------------------------------------------- \n line", i)
            im_x = img

            #bi_point_indexes = np.nonzero(line2Line[i, :] > 0)[0]
            bi_point_indexes = np.nonzero(mutual_T12[i, :] > -1)[0]
            single_point_indexes = np.nonzero(back_T12[i, :] > -1)[0]
            online_point_indexes = np.nonzero(within_T12[i, :] > -1)[0]

            bx, by = line_2_mix[i, 0], line_2_mix[i, 1]
            px, py = line_2_mix[i, 2], line_2_mix[i, 3]
            k = line_2_map_junction[i]

            if distance((px, py), (bx, by)) < 0.05 * max_side_length:
                lines_5.append((px, py, bx, by))
                im_5 = addLines(im_5, [(px, py, bx, by)], display_=False, rand_color=False,
                                color=(40, 255, 0), thickness=2)
                if DEBUG:
                    showIm(img=im_x, name='Line i')
                    showIm(img=im_5, name='Line 3')
                continue

            if len(bi_point_indexes) == 0 and len(online_point_indexes) == 0:
                im_x = addPoints(im_x, junctions[k:k + 1], display_=False, thickness=3,
                                 color=(255, 0, 0))
                im_x = addLines(im_x, line_2_mix[i:i + 1], display_=False, rand_color=False,
                                color=(0, 255, 0), thickness=2)

                ratio, max_loc, _ = pixelRatio((px, py), (bx, by), m3)
                if ratio < 0.05:
                    continue

                bx, by = max_loc

                intersects = intersections(
                    np.array([px, py, bx, by], dtype=np.float32),
                    np.array(lines_1, dtype=np.float32))
                if DEBUG:
                    im_5 = addPoints(im_5, intersects, display_=False, thickness=3, color=(0, 0,
                                                                                           255))
                im_x = addPoints(im_x, intersects, display_=False, thickness=3, color=(0, 0, 255))

                if DEBUG:
                    print("Intersects.", len(intersects))

                start_list = [(px, py)]
                end_list = []

                for int_ in intersects:
                    start_list.append(int_)
                    end_list.append(int_)
                end_list.append((bx, by))

                next_start = None
                previous_end = None

                first_flag = True
                for idx, (start, end) in enumerate(zip(start_list, end_list)):
                    if not first_flag:
                        break

                    if next_start is None:
                        next_start = start

                    line_ratio, max_pos_idx, max_pos_loc = pixelRatio(start, end, m3)
                    if DEBUG:
                        print("       distance of start, end ", distance(start, end), " ratio: ",
                              line_ratio)
                    adding_line = False

                    valid_cond = line_ratio > 0.6 and max_pos_loc > 0.75
                    if idx == 0:
                        if distance(start, end) < max_side_length / 20. or valid_cond:
                            adding_line = True
                    elif valid_cond:
                        adding_line = True

                    if adding_line:
                        # if DEBUG:
                        #    print "distance of start, end ", distance(start, end), " ratio: ", line_ratio
                        previous_end = end
                        im_x = addLines(im_x, [(start[0], start[1], end[0], end[1])],
                                        display_=False, rand_color=False, color=(255, 0,
                                                                                 255), thickness=2)
                        im_5 = addLines(im_5, [(start[0], start[1], end[0], end[1])],
                                        display_=False, rand_color=False, color=(40, 255,
                                                                                 0), thickness=2)
                        lines_5.append((start[0], start[1], end[0], end[1]))

                        if DEBUG:
                            showIm(img=im_x, name='Line i')
                            showIm(img=im_5, name='Line 3')
                    else:
                        # if previous_end is not None:
                        #    lines_3.append((next_start[0], next_start[1], previous_end[0], previous_end[1]))
                        if idx == 0:
                            first_flag = False
                        next_start = None
                        previous_end = None

            elif len(bi_point_indexes) == 0 and len(online_point_indexes) > 0:
                im_x = addPoints(im_x, junctions[k:k + 1], display_=False, thickness=3,
                                 color=(255, 0, 0))
                im_x = addLines(im_x, line_2_mix[i:i + 1], display_=False, rand_color=False,
                                color=(0, 255, 0), thickness=2)

                #perps = [perp_points_12[p_idx, i] for p_idx in online_point_indexes]

                im_x = addPoints(im_x, junctions[online_point_indexes], display_=False,
                                 thickness=3, color=(0, 0, 255))
                online_point_indexes = online_point_indexes.tolist()
                online_point_indexes.sort(key=lambda x: distance(perp_points_12[x, i], (px, py)))

                ratio, max_loc, _ = pixelRatio((px, py), (bx, by), m3)
                if ratio < 0.05:
                    continue
                bx, by = max_loc

                start_list = [(px, py)]
                end_list = []

                if DEBUG:
                    print("online points: ", len(online_point_indexes))

                for on_idx in online_point_indexes:
                    start_list.append(perp_points_12[on_idx, i])
                    end_list.append(perp_points_12[on_idx, i])
                end_list.append((bx, by))

                next_start = None
                previous_end = None
                for idx, (start, end) in enumerate(zip(start_list, end_list)):
                    if next_start is None:
                        next_start = start

                    line_ratio, max_pos_idx, max_pos_loc = pixelRatio(start, end, m3)
                    if DEBUG:
                        print("       distance of start, end ", distance(start, end), " ratio: ",
                              line_ratio)
                    adding_line = False

                    valid_cond = line_ratio > 0.6 and max_pos_loc > 0.75

                    if idx == 0:
                        if distance(start, end) < max_side_length / 20. or valid_cond:
                            #lines_3.append((start[0], start[1], end[0], end[1]))
                            adding_line = True
                    elif valid_cond:
                        #lines_3.append((start[0], start[1], end[0], end[1]))
                        adding_line = True

                    if adding_line:
                        previous_end = end
                        # if DEBUG:
                        #    print "distance of start, end ", distance(start, end), " ratio: ", line_ratio

                        im_x = addLines(im_x, [(start[0], start[1], end[0], end[1])],
                                        display_=False, rand_color=False, color=(255, 0,
                                                                                 255), thickness=2)
                        im_5 = addLines(im_5, [(start[0], start[1], end[0], end[1])],
                                        display_=False, rand_color=False, color=(40, 255,
                                                                                 0), thickness=2)
                        lines_5.append((start[0], start[1], end[0], end[1]))
                        if DEBUG:
                            showIm(img=im_x, name='Line i')
                            showIm(img=im_5, name='Line 3')
                    else:
                        # if previous_end is not None:
                        #    lines_3.append((next_start[0], next_start[1], previous_end[0], previous_end[1]))

                        next_start = None
                        previous_end = None

                if DEBUG:
                    showIm(img=im_x, name='Line i')

        if save_t22_5:
            print("lines_5: ", len(lines_5))
            res_5 = addLines(res_1, lines_5, display_=False, rand_color=False, color=(0, 255, 0)
                             if phase == 'final' else (122, 0, 125), thickness=2)
            cv2.imwrite(join(save_dir, in_ + '_t22_5.png'), res_5)
            np.save(join(line_save_dir, in_ + '_line_5.npy'), np.array(lines_1 + lines_5))


def intersections(line, lines_all):
    p = line[:2]

    intersects = []
    for la in lines_all:
        intersect = intersectionOfTwoLines(line, la)
        if intersect is None:
            continue
        ip1 = np.inner(line[:2] - intersect, line[2:] - intersect)
        ip2 = np.inner(la[:2] - intersect, la[2:] - intersect)
        if ip1 >= 0 or ip2 >= 0:
            continue
        intersects.append(intersect)
    intersects.sort(key=lambda x: ((x[0] - p[0])**2 + (x[1] - p[1])**2))
    nodup = []
    for i, it_ in enumerate(intersects):
        dup_flag = False
        dup_idx = None
        for j, nd_ in enumerate(nodup):
            if distance(it_, nd_) < 3.:
                dup_flag = True
                dup_idx = j
                break
        if not dup_flag:
            nodup.append(it_)

    return nodup


def pixelRatio(p1, p2, M):
    coords = linespace(p1, p2, M.shape)
    map_value = M[coords]
    # print "\n map_value: ", map_value, "\n"

    ratio, max_idx_loc, max_idx = ratioSeq(map_value)
    max_idx = int(max_idx)
    if len(coords[0]) == 0:
        return 0, p1

    locx = coords[1][max_idx]
    locy = coords[0][max_idx]

    return ratio, (locx, locy), max_idx_loc


def ratioSeq(seq):
    num = len(seq)
    nz_indexes = np.nonzero(seq)[0]
    if len(nz_indexes) == 0:
        return 0., 0., 0.
    max_idx = nz_indexes.max()
    # print "num of numzeros ", len(nz_indexes), " max_idx: ", max_idx

    return float(len(nz_indexes)) / float(max_idx + 1), float(max_idx + 1) / float(num), max_idx


def linespace(p1, p2, shape):
    x1, y1 = p1
    x2, y2 = p2
    h, w = shape

    x1, y1 = int(x1), int(y1)
    x2, y2 = int(x2), int(y2)

    x1 = min(max(x1, 0), w - 1)
    x2 = min(max(x2, 0), w - 1)
    y1 = min(max(y1, 0), h - 1)
    y2 = min(max(y2, 0), h - 1)

    #xlist = np.arange(x1, x2, 1)
    #ylist = np.arange(y1, y2, 1)
    num_x = max(x1, x2) - min(x1, x2) + 1
    num_y = max(y1, y2) - min(y1, y2) + 1

    # print w, h, x1, x2, y1, y2
    if num_x < num_y:
        xlist = np.linspace(x1, x2, num=num_y)
        ylist = np.linspace(y1, y2, num=num_y)
    else:
        xlist = np.linspace(x1, x2, num=num_x)
        ylist = np.linspace(y1, y2, num=num_x)

    xlist = xlist.astype(np.int32)
    ylist = ylist.astype(np.int32)

    ylist[ylist > (h - 1)] = h - 1
    xlist[xlist > (w - 1)] = w - 1
    coords = np.vstack((ylist, xlist))
    return tuple(coords)


def test_linespace():
    linespace((1, 100), (60, 70))


def twoLinesIntersectInMiddle(A, B):
    intersect = intersectionOfTwoLines(A, B)
    if intersect is None:
        return False
    ip1 = np.inner(A[:2] - intersect, A[2:] - intersect)
    ip2 = np.inner(B[:2] - intersect, B[2:] - intersect)
    if ip1 <= 0 and ip2 <= 0:
        return True
    else:
        return False


def intersectionWithIntervals(in_, intervals):
    xs, xe = in_

    def getoverlap(b):
        return max(0, min(xe, b[1]) - max(xs, b[0]))

    inters_ = 0.
    for it in intervals:
        inters_ = getoverlap(it)
        if inters_ > 0:
            return True
            break
    return True if inters_ > 0 else False


def angleBetweenLines(l1, l2):
    x = l1[:2] - l1[2:4]
    y = l2[:2] - l2[2:4]
    theta = np.arccos(
        np.clip(innerProduct(x, y) / (np.linalg.norm(x) * np.linalg.norm(y) + eps), -1.,
                1.)) * 180. / pi
    return np.minimum(theta, 180. - theta)


def angleBetweenLinesMatrix(L1, L2):
    M, N = L1.shape[0], L2.shape[0]
    x = L1[:, :2] - L1[:, 2:4]
    y = L2[:, :2] - L2[:, 2:4]
    x = x[:, np.newaxis, :]
    y = y[np.newaxis, :, :]

    theta = np.arccos(
        np.clip(
            innerProduct(x, y) / (np.linalg.norm(x, axis=-1) * np.linalg.norm(y, axis=-1) + eps),
            -1., 1.)) * 180. / pi
    return np.minimum(theta, 180. - theta)


def cutLines(connection_matrix, within_matrix, lines, points, img=None, DEBUG=False):
    M = lines.shape[0]
    N = points.shape[0]
    assert connection_matrix.shape == (M, N)

    cut_lines = np.copy(lines)
    for i in range(M):
        x1, y1, x2, y2 = lines[i].tolist()
        point_indexes = within_matrix[i, :]
        point_indexes = np.nonzero(point_indexes == True)[0]

        if len(point_indexes) <= 1:
            continue
        else:
            lengths = [(k, (x1 - points[k][0])**2 + (y1 - points[k][1])**2) for k in point_indexes]
            lengths.sort(key=lambda x: x[1])
            #endpoint_idx = point_indexes[max_idx]
            #endpoint_idx = lengths[0 if len(lengths) == 1 else 1][0]
            #endpoint_idx = lengths[len(lengths)/2][0]
            endpoint_idx = lengths[0][0]

            im = addLines(img, lines[i:i + 1], display_=False, color=(0, 0, 255))
            im = addPoints(im, [points[k] for k in point_indexes], display_=False
                           if DEBUG else False)
            im = addPoints(im, [points[endpoint_idx]], display_=False, color=(0, 0, 0))
            cut_lines[i, :2] = points[endpoint_idx, :]
            im = addLines(im, cut_lines[i:i + 1], display_=True
                          if DEBUG else False, color=(0, 255, 0))

    return cut_lines


def convertRawGt():
    src_dir = join(home, 'ws/dataset/zihan_version_simple_data/')
    save_dir = 'test'
    filenames = [x[:-4] for x in listdir('test') if x.endswith('.jpg')]
    loadRawGt(src_dir, filenames, save_dir)


def do_nothing():
    print("do nothing.")
    pass


def _thinningIteration(im, iter):
    I, M = im, np.zeros(im.shape, np.uint8)
    expr = """
    for (int i = 1; i < NI[0]-1; i++) {
        for (int j = 1; j < NI[1]-1; j++) {
            int p2 = I2(i-1, j);
            int p3 = I2(i-1, j+1);
            int p4 = I2(i, j+1);
            int p5 = I2(i+1, j+1);
            int p6 = I2(i+1, j);
            int p7 = I2(i+1, j-1);
            int p8 = I2(i, j-1);
            int p9 = I2(i-1, j-1);

            int A  = (p2 == 0 && p3 == 1) + (p3 == 0 && p4 == 1) +
                     (p4 == 0 && p5 == 1) + (p5 == 0 && p6 == 1) +
                     (p6 == 0 && p7 == 1) + (p7 == 0 && p8 == 1) +
                     (p8 == 0 && p9 == 1) + (p9 == 0 && p2 == 1);
            int B  = p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9;
            int m1 = iter == 0 ? (p2 * p4 * p6) : (p2 * p4 * p8);
            int m2 = iter == 0 ? (p4 * p6 * p8) : (p2 * p6 * p8);

            if (A == 1 && B >= 2 && B <= 6 && m1 == 0 && m2 == 0) {
                M2(i,j) = 1;
            }
        }
    }
    """

    weave.inline(expr, ["I", "iter", "M"])
    return (I & ~M)


def thinning(src):
    dst = src.copy() / 255
    prev = np.zeros(src.shape[:2], np.uint8)
    diff = None

    while True:
        dst = _thinningIteration(dst, 0)
        dst = _thinningIteration(dst, 1)
        diff = np.absolute(dst - prev)
        prev = dst.copy()
        if np.sum(diff) == 0:
            break

    return dst * 255


def get_lines(img, thresh=10, rho=1.8):
    img[img < thresh] = 0
    img[img >= thresh] = 255
    lines = cv2.HoughLinesP(img, rho, np.pi / 180, 50)
    return lines[:, 0, :], img


def testThin():
    imgname = "00051831"
    src = cv2.imread("1/%s_edge.png" % imgname, 0)
    _, bw2 = cv2.threshold(src, 10, 255, cv2.THRESH_BINARY)
    bw2 = thinning(bw2)
    origin_img = cv2.imread("samples/test/%s.jpg" % imgname)

    lines1, img1 = get_lines(src)
    lines2, img2 = get_lines(bw2, rho=1.6)
    print(lines1.shape, lines2.shape)
    print(origin_img.shape)

    origin_img = cv2.resize(origin_img, (256, 256))

    im1 = addLines(origin_img, lines1, display_=False, rand_color=True, color=(0, 0, 255),
                   thickness=2)
    im2 = addLines(origin_img, lines2, display_=False, rand_color=True, color=(0, 0, 255),
                   thickness=2)
    cv2.imshow("thick", im1)
    cv2.imshow("thinning", im2)

    #cv2.imshow("thick", cv2.threshold(src, 5, 255, cv2.THRESH_BINARY)[1])
    #cv2.imshow("thinning", bw2)
    cv2.waitKey()
    raise


def main():
    #loadData('2.4', 25, 4)
    # convertRawGt()
    # testYork()
    # testThin()

    with open('txt/exp2.txt', 'r') as f:
        exps = f.read().splitlines()
        #exps = ['5.1 32', '6.1 32']
        #exps = ['2.13 32']
        #exps = ['9.1 30']
        exps = ['9.2 5']
        exps = ['9.3 8']
        exps = ['9.4 10', '9.4 12', '9.4 14']
        #exps = ['2.12 30']
        # , '5.1 32', '6.1 32']
        for exp in exps:
            exp_id, iteration = exp.split(' ')
            iteration = int(iteration)
            #proposeLines(exp_id, iteration)
            saveJunction(exp_id, iteration, dataset_name='bsds')
            #saveJunctionTheta(exp_id, iteration)

            #loadData(exp_id, iteration, 0)
            #calcResidual(exp_id, iteration, 4)
            #calcMissing(exp_id, iteration, 4)
            #thetaGrouping(exp_id, iteration, 0)


if __name__ == '__main__':
    main()
