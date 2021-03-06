import argparse
import datetime
import os
import cv2

import numpy as np
import PanoramaStitching.Stitcher as Stitcher
import PanoramaStitching.Utils as PanoUtils
from PanoramaStitching.Logger import LogLevel
from PanoramaStitching.Logger import logger_instance
from PanoramaStitching.Matcher import KeyPointDetector
from PanoramaStitching.Matcher import Matcher
from PanoramaStitching.PanoramaImage import MainPanoramaImage

# Because of Windows
import sys

sys.path.append("./")

# Parser
parser = argparse.ArgumentParser(description='Panorama stitching.')
parser.add_argument('--folder',
                    required=True,
                    help='path to file with images')
parser.add_argument('--img',
                    required=True,
                    help='path to main image')
parser.add_argument('--dest',
                    required=True,
                    help='destination of output image')
parser.add_argument('--out',
                    help='destination of debug output')

parser.add_argument('--kp_detector',
                    default='SIFT',
                    choices=['SIFT', 'SURF'],
                    help='key point detector SIFT or SURF')

parser.add_argument('--pano_type',
                    default='HOMOGRAPHY',
                    choices=['HOMOGRAPHY', 'AFFINE'],
                    help='type of panorama HOMOGRAPHY or AFFINE')
parser.add_argument('--cyl_wrap', default=False,
                    action='store_true',
                    help='Wrap images on a cylinder')

parser.add_argument('--blender',
                    default='None',
                    choices=['None', 'weight', 'graph_cut'],
                    help='key point detector SIFT or SURF')

parser.add_argument('--debug', default=False,
                    action='store_true',
                    help='Allow debug prints')


def print_image_info(images):
    """
    Print info about images used in a panorama
    :param images: list of PanoramaImage
    """

    # Print images used in panorama
    logger_instance.log(LogLevel.INFO, "List of images used in panorama:")
    for img in images:
        if img.checked:
            logger_instance.log(LogLevel.NONE, "\t\t" + img.name)

    # Print not used images in panorama
    logger_instance.log(LogLevel.INFO, "List of images NOT used in panorama:")
    for img in images:
        if not img.checked:
            logger_instance.log(LogLevel.NONE, "\t\t" + img.name)


def panorama_loop(args, images, panorama_image):
    """
    Main loop of the panorama stitching. Finds the most viable image and stitches it to the panorama.
    Ends when conditions for stitching aren't met.
    :param args: program arguments
    :param images: list of PanoramaImage
    :param panorama_image: main panorama image
    """
    added = True
    cnt = 0
    logger_instance.log(LogLevel.STATUS, "Starting main panorama loop")
    while added:
        added = False

        # Calculate descriptors and best matches
        panorama_image.calculate_descriptors(matcher)
        panorama_image.calculate_matches(images, matcher, args.pano_type.lower())
        match_count, index = panorama_image.find_best_match()

        logger_instance.log(LogLevel.DEBUG, "Index: " + str(index) + " Cnt: " + str(match_count))

        if not index == -1:
            logger_instance.log(LogLevel.INFO, "Stitching with: " + panorama_image.matches[index][1].name)

            # Use homography or affine transformation
            matches, h, status = panorama_image.matches[index][0]

            panorama_image.image, panorama_image.mask = Stitcher.stitch_images(panorama_image.image,
                                                          panorama_image.mask,
                                                          panorama_image.matches[index][1].image,
                                                          panorama_image.matches[index][1].mask,
                                                          h,
                                                          args.pano_type.lower(),
                                                          args.blender.lower())
            # Changed image, continue
            panorama_image.matches[index][1].checked = True
            added = True
            if args.debug:
                save_location = args.out + str(cnt) + ".png"
                logger_instance.log(LogLevel.DEBUG, "saving intermediate result to: " + save_location)
                cv2.imwrite(save_location, panorama_image.image)
            cnt += 1
            logger_instance.log(LogLevel.STATUS, "Matched " + str(cnt + 1) + "/" + str(len(images)) + " images")


def panorama(args, main_image, images):
    """
    Homography panorama.
    :param args: program arguments
    :param main_image: main panorama image
    :param images: list of PanoramaImage
    """

    # Calculate descriptors
    logger_instance.log(LogLevel.STATUS, "Calculating image descriptors... ")
    f = 750
    for img in images:
        if args.cyl_wrap:
            h, w = img.image.shape[:2]
            K = np.array([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1]])

            # Geometrically transform image and add border
            mask = np.ones(img.image.shape, dtype=np.uint8) * 255
            img.image = Stitcher.wrap_image_on_cylinder(img.image, K)[0]
            img.mask = Stitcher.wrap_image_on_cylinder(mask, K)[0]
            if main_image.name == img.name:
                main_image.mask = img.mask
        img.calculate_descriptors(matcher)
    logger_instance.log(LogLevel.STATUS, "Calculating image descriptors... Done")

    # Get main panorama image
    panorama_image = MainPanoramaImage(main_image.name, main_image.image, main_image.mask)
    main_image.checked = True

    # Create wonderful panorama
    panorama_loop(args, images, panorama_image)

    """
    # Global color reduction
    logger_instance.log(LogLevel.STATUS, "Color balancing...")
    panorama_image.image = PanoUtils.balance_global_image(panorama_image.image)
    logger_instance.log(LogLevel.STATUS, "Color balancing... Done.")
    """

    logger_instance.log(LogLevel.STATUS, "Saving finished panorama image")
    logger_instance.log(LogLevel.INFO, "Final image location: " + args.dest)
    cv2.imwrite(args.dest, panorama_image.image)

    # Save created panorama
    print_image_info(images)


def main(args):
    logger_instance.set_debug(args.debug)

    # Setup key point detectors
    global matcher
    if args.kp_detector == 'SIFT':
        logger_instance.log(LogLevel.STATUS, "Using SIFT key point detector")
        matcher = Matcher(KeyPointDetector.SIFT, 4)
    elif args.kp_detector == 'SURF':
        logger_instance.log(LogLevel.STATUS, "Using SURF key point detector")
        matcher = Matcher(KeyPointDetector.SURF, 4)

    logger_instance.log(LogLevel.STATUS, "Using " + args.pano_type + " transform")

    if args.cyl_wrap:
        logger_instance.log(LogLevel.STATUS, "Using cylinder projection on images")

    # Load images in gained folder
    images = PanoUtils.load_images(args.folder)
    logger_instance.log(LogLevel.INFO, "Images in folder:")
    for img in images:
        # Log file name
        logger_instance.log(LogLevel.NONE, "\t\t" + img.name)

    for x in images:
        # Check if file exists
        if x.name == os.path.basename(args.img):
            break
    else:
        # Nope
        x = None

    if x is None:
        logger_instance.log(LogLevel.ERROR, "File \"" + os.path.basename(args.img) + "\" not found")
        return

    # Set main image
    main_image = x
    logger_instance.log(LogLevel.INFO, "Main image:")
    logger_instance.log(LogLevel.NONE, "\t\t" + main_image.name)

    # Color balancing of all images
    #logger_instance.log(LogLevel.STATUS, "Color balancing...")
    #images = PanoUtils.balance_color(images, main_image.image)
    #logger_instance.log(LogLevel.STATUS, "Color balancing... Done.")

    # Call panorama stitcher
    panorama(args, main_image, images)


if __name__ == "__main__":
    # Save start time of the process
    start_time = datetime.datetime.now()

    # Call main function
    try:
        main(parser.parse_args())
    except Exception as e:
        logger_instance.log_exc(e)

    # Done, write end time and close app
    end_time = datetime.datetime.now()
    logger_instance.log(LogLevel.INFO, "Total execution time: " + str((end_time - start_time)))
