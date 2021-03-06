import math

import cv2
import numpy as np

from PanoramaStitching import Blender
from PanoramaStitching.Logger import logger_instance, LogLevel
from PanoramaStitching import SeamFinding


def wrap_image_on_cylinder(img1, K):
    """
    Wraps image on a cylinder defined by matrix K (http://ksimek.github.io/2013/08/13/intrinsic/).
    :param img1: image to wrap
    :param K: intrinsic matrix
    :return: transformed image
    """
    f = K[0, 0]

    im_h, im_w = img1.shape[:2]

    cyl = np.zeros_like(img1)
    cyl_mask = np.zeros_like(img1)
    cyl_h, cyl_w = cyl.shape[:2]
    x_c = float(cyl_w) / 2.0
    y_c = float(cyl_h) / 2.0
    for x_cyl in np.arange(0, cyl_w):
        for y_cyl in np.arange(0, cyl_h):
            theta = (x_cyl - x_c) / f
            h = (y_cyl - y_c) / f

            X = np.array([math.sin(theta), h, math.cos(theta)])
            X = np.dot(K, X)
            x_im = X[0] / X[2]
            if x_im < 0 or x_im >= im_w:
                continue

            y_im = X[1] / X[2]
            if y_im < 0 or y_im >= im_h:
                continue

            cyl[int(y_cyl), int(x_cyl)] = img1[int(y_im), int(x_im)]
            cyl_mask[int(y_cyl), int(x_cyl)] = 255

    return cyl, cyl_mask


def stitch_images(img1, mask1, img2, mask2, matrix, transformation_type, blender_type):
    """
    Stitch images using affine warp.
    :param transformation_type: homography or affine
    :param img1: panorama image
    :param img2: image to stitch
    :param matrix: affine/homography matrix
    :return: stitched image
    """

    if mask2 is None:
        mask2 = np.ones(img2.shape, dtype=np.uint8) * 255

    rows1, cols1 = img1.shape[:2]
    rows2, cols2 = img2.shape[:2]

    list_of_points_1 = np.float32([[0, 0], [0, rows1], [cols1, rows1], [cols1, 0]]).reshape(-1, 1, 2)
    temp_points = np.float32([[0, 0], [0, rows2], [cols2, rows2], [cols2, 0]]).reshape(-1, 1, 2)

    if transformation_type == "affine":
        list_of_points_2 = cv2.transform(temp_points, matrix)
    elif transformation_type == "homography":
        list_of_points_2 = cv2.perspectiveTransform(temp_points, matrix)
    else:
        raise Exception("Invalid call, unsupported transformation type: " + transformation_type)
    list_of_points = np.concatenate((list_of_points_1, list_of_points_2), axis=0)

    [x_min, y_min] = np.int32(list_of_points.min(axis=0).ravel() - 0.5)
    [x_max, y_max] = np.int32(list_of_points.max(axis=0).ravel() + 0.5)

    translation_dist = [-x_min, -y_min]
    if transformation_type == "affine":
        matrix = np.vstack([matrix, [0, 0, 1]])
    h_translation = np.array([[1, 0, translation_dist[0]], [0, 1, translation_dist[1]], [0, 0, 1]])

    output_img = cv2.warpPerspective(img2, h_translation.dot(matrix), (x_max - x_min, y_max - y_min))
    mask2 = cv2.warpPerspective(mask2, h_translation.dot(matrix), (x_max - x_min, y_max - y_min))

    temp_image = np.zeros((y_max - y_min, x_max - x_min, 3), np.uint8)

    if mask1 is None:
        mask1 = np.ones(img1.shape, dtype=np.uint8) * 255

    tmp_mask = np.zeros(temp_image.shape, dtype=np.uint8)

    temp_image[translation_dist[1]:rows1 + translation_dist[1],
    translation_dist[0]:cols1 + translation_dist[0]] = img1

    tmp_mask[translation_dist[1]:rows1 + translation_dist[1],
    translation_dist[0]:cols1 + translation_dist[0]] = mask1

    mask1 = np.copy(tmp_mask)

    width, height, _ = temp_image.shape

    panorama_mid_point = np.int32(list_of_points_1[2] / 2 - translation_dist)
    to_add_mid_point = np.int32(list_of_points_2[2] - (list_of_points_2[2] - list_of_points_2[0]) / 2)

    if blender_type == "graph_cut":
        temp_image = SeamFinding.graph_cut_blend(temp_image, mask1, output_img, mask2, panorama_mid_point, to_add_mid_point)
    elif blender_type == "weight":
        temp_image = Blender.weighted_compositing(temp_image, mask1, output_img, mask2, panorama_mid_point, to_add_mid_point)
    else:
        temp_image = Blender.simple_overlay(temp_image, mask1, output_img, mask2)

    mask1 = cv2.bitwise_or(mask1, mask2)

    return temp_image, mask1
