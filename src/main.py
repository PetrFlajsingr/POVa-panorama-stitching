import string
import sys
import cv2
import numpy as np
import argparse
import glob
import os

sift = cv2.xfeatures2d.SIFT_create()
matcher = cv2.DescriptorMatcher_create("BruteForce")

parser = argparse.ArgumentParser(description='Panorama stitching.')
parser.add_argument('--folder', help='path to file with images')
parser.add_argument('--img', help='path to main image')
parser.add_argument('--dest', help='destination of output image')


def load_images(folder):
    """
    Get list of images in a folder
    :param folder: folder containing images
    :return: list of images and their names
    """
    filenames = glob.glob(folder + "/*.png")
    images = [cv2.cvtColor(cv2.imread(img), cv2.COLOR_BGR2GRAY) for img in filenames]
    ret = []
    for i in range(len(filenames)):
        ret.append([images[i], os.path.basename(filenames[i])])
    return ret


def get_sift(image):
    """
    Get key points detected by SIFT
    :param image: input image
    """
    gray_scale_image = image
    key_points, descriptors = sift.detectAndCompute(gray_scale_image, None)

    key_points = np.float32([key_point.pt for key_point in key_points])
    return key_points, descriptors


def match_keypoints(key_points_a, key_points_b, descriptors_a, descriptors_b,
                    ratio, threshold):
    """
    match key points given by SIFT
    :param key_points_a: key points of first image
    :param key_points_b: key points of second image
    :param descriptors_a: descriptors of first image
    :param descriptors_b: descriptors of second image
    :param ratio:
    :param threshold:
    :return: matches and homography if
    """
    raw_matches = matcher.knnMatch(descriptors_a, descriptors_b, 2)
    matches = []

    for m in raw_matches:
        if len(m) == 2 and m[0].distance < m[1].distance * ratio:
            matches.append((m[0].trainIdx, m[0].queryIdx))

    if len(matches) > 100:
        points_a = np.float32([key_points_a[i] for (_, i) in matches])
        points_b = np.float32([key_points_b[i] for (i, _) in matches])

        (H, status) = cv2.findHomography(points_a, points_b, cv2.RANSAC,
                                         threshold)

        return matches, H, status

    return None


def show_matches(image_a, image_b, key_points_a, key_points_b, matches, status):
    """
    Show window with matched keypoints
    :param image_a: first image
    :param image_b: second image
    :param key_points_a: key points of the first image
    :param key_points_b: key points of the second image
    :param matches:
    :param status:
    """
    (hA, wA) = image_a.shape[:2]
    (hB, wB) = image_b.shape[:2]
    result = np.zeros((max(hA, hB), wA + wB), dtype="uint8")
    result[0:hA, 0:wA] = image_a
    result[0:hB, wA:] = image_b

    for ((trainIdx, queryIdx), s) in zip(matches, status):
        if s == 1:
            point_a = (int(key_points_a[queryIdx][0]), int(key_points_a[queryIdx][1]))
            point_b = (int(key_points_b[trainIdx][0]) + wA, int(key_points_b[trainIdx][1]))
            cv2.line(result, point_a, point_b, (0, 255, 0), 1)

    cv2.imshow('matches', result)
    cv2.waitKey()


def stitch_images(image_a, image_b, hom):
    """
    Warp image_b by given matrix (hom) and stitch it together with image_a
    :param image_a: first image
    :param image_b: second image
    :param hom: homography matrix
    :return: stitched image
    """
    result = cv2.warpPerspective(image_a, hom, (image_a.shape[1] + image_b.shape[1], image_a.shape[0]))
    result[0:image_b.shape[0], 0:image_b.shape[1]] = image_b
    return result


def crop_black(image):
    """
    Crop black parts of the image
    :param image: input image
    :return: cropped image
    """
    _, thresh = cv2.threshold(image, 1, 255, cv2.THRESH_BINARY)
    _, contours, hierarchy = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnt = contours[0]
    x, y, w, h = cv2.boundingRect(cnt)

    crop = image[y:y + h, x:x + w]
    return crop


def warpImages(img1, img2, H):
    rows1, cols1 = img1.shape[:2]
    rows2, cols2 = img2.shape[:2]

    list_of_points_1 = np.float32([[0, 0], [0, rows1], [cols1, rows1], [cols1, 0]]).reshape(-1, 1, 2)
    temp_points = np.float32([[0, 0], [0, rows2], [cols2, rows2], [cols2, 0]]).reshape(-1, 1, 2)

    list_of_points_2 = cv2.perspectiveTransform(temp_points, H)
    list_of_points = np.concatenate((list_of_points_1, list_of_points_2), axis=0)

    [x_min, y_min] = np.int32(list_of_points.min(axis=0).ravel() - 0.5)
    [x_max, y_max] = np.int32(list_of_points.max(axis=0).ravel() + 0.5)

    translation_dist = [-x_min, -y_min]
    H_translation = np.array([[1, 0, translation_dist[0]], [0, 1, translation_dist[1]], [0, 0, 1]])

    output_img = cv2.warpPerspective(img2, H_translation.dot(H), (x_max - x_min, y_max - y_min))
    output_img[translation_dist[1]:rows1 + translation_dist[1], translation_dist[0]:cols1 + translation_dist[0]] = img1
    return output_img


def main(args):
    images = load_images(args.folder)
    addedFlags = [False for img in images]

    panorama = images[8][0]
    addedFlags[8] = True
    print("[INFO] Base image:" + images[0][1])
    added = True
    cnt = 0
    while added:
        added = False
        for i in range(len(images)):
            if addedFlags[i]:
                continue
            print("[INFO] Current image:" + images[i][1])
            kp_a, desc_a = get_sift(panorama)
            kp_b, desc_b = get_sift(images[i][0])
            m = match_keypoints(kp_a, kp_b, desc_a, desc_b, 0.75, 4.5)
            if m is None:
                continue
            added = True
            addedFlags[i] = True
            matches, H, status = m

            panorama = warpImages(images[i][0], panorama, H)
            panorama = crop_black(panorama)
            cv2.imwrite("/Users/petr/Desktop/images/output/out" + str(cnt) + ".png", panorama)
            cnt += 1
            print("[INFO] " + str(i) + "/" + str(len(images) - 1))
        print("[INFO] next iteration")
    print("[INFO] stitching done")

    cv2.imwrite(args.dest, panorama)
    cv2.waitKey()


if __name__ == "__main__":
    main(parser.parse_args())