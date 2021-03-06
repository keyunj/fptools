"""
This file (uni_keypoints.py) is designed for:
    functions for keypoints
Copyright (c) 2021, Yongjie Duan. All rights reserved.
"""
import os
import sys

# os.chdir(sys.path[0])
import os.path as osp
import numpy as np
from glob import glob
import cv2
from scipy import io as sio, ndimage as ndi

from .uni_io import mkdir


# def convert_My_Neu_to_Mcc(src_dir, tar_dir, kps_name):
#     mnt, img_shape = load_minutiae(osp.join(src_dir, f"{kps_name}.mnt"), return_hearder=True)
#     mkdir(tar_dir)
#     if not osp.exists(osp.join(tar_dir, f"{kps_name}.txt")):
#         with open(osp.join(tar_dir, f"{kps_name}.txt"), "w") as fp:
#             fp.write(f"{img_shape[0]}\n{img_shape[1]}\n500\n{len(mnt)}\n")
#             for cur in mnt:
#                 fp.write(f"{cur[0]} {cur[1]} {2 * np.pi - cur[2] * np.pi/180}\n")


def solve_rigid_transformation(mnts1, mnts2):
    mnts1_mean = mnts1.mean(0)
    mnts2_mean = mnts2.mean(0)
    mnts1_c = mnts1 - mnts1_mean[None]
    mnts2_c = mnts2 - mnts2_mean[None]

    cov = np.dot(mnts1_c.T, mnts2_c)
    U, S, Vh = np.linalg.svd(cov)
    R = Vh.T.dot(U.T)
    t = mnts2_mean - R.dot(mnts1_mean)
    return R, t


def generate_heatmap(img_shape, kps, factor=8, radius=3):
    heatmap = np.zeros(img_shape)
    for kp in kps:
        cur_kp = np.rint(kp * 1.0 / factor).astype(int)
        cur_kp[0] = cur_kp[0].clip(0, img_shape[1] - 1)
        cur_kp[1] = cur_kp[1].clip(0, img_shape[0] - 1)
        heatmap[np.rint(cur_kp[1]).astype(int), np.rint(cur_kp[0]).astype(int)] = 1
    if len(kps):
        heatmap = np.exp(-ndi.morphology.distance_transform_edt(1 - heatmap) ** 2 / (2 * radius ** 2))
    return heatmap


def remove_wrond_matches(kps1, kps2, ransacReprojThreshold=10, returnH=False):
    if kps1.shape[-1] == 2:
        H, status = cv2.estimateAffinePartial2D(
            kps1[:, None], kps2[:, None], method=cv2.RANSAC, ransacReprojThreshold=ransacReprojThreshold
        )
        # H, status = cv2.findHomography(
        #     kps1[:, None], kps2[:, None], method=cv2.RANSAC, ransacReprojThreshold=ransacReprojThreshold
        # )
    elif kps1.shape[-1] == 3:
        H, status = cv2.estimateAffine3D(kps1[:, None], kps2[:, None], ransacReprojThreshold=ransacReprojThreshold)
    else:
        raise ValueError(f"unsopported dimension {kps1.shape[-1]}")
    # return kps1[status[:, 0] > 0,], kps2[status[:, 0] > 0,]
    if returnH:
        return status[:, 0] > 0, H
    else:
        return status[:, 0] > 0


def remove_outside_keypoints(kps, seg):
    flags = ndi.map_coordinates(seg, (kps[:, 1], kps[:, 0]), order=0) > 0
    return flags > 0


def remove_outside_matches(kps1, kps2, mask1=None, mask2=None, min_kps=10):
    assert len(kps1) == len(kps2)
    kps1 = np.round(kps1).astype(int)
    kps2 = np.round(kps2).astype(int)

    remove_ids = []
    for ii in range(len(kps1)):
        if (
            (kps1[ii, 0] < 0 or kps1[ii, 0] >= mask1.shape[1])
            or (kps1[ii, 1] < 0 or kps1[ii, 1] >= mask1.shape[0])
            or (kps2[ii, 0] < 0 or kps2[ii, 0] >= mask2.shape[1])
            or (kps2[ii, 1] < 0 or kps2[ii, 1] >= mask2.shape[0])
            or (mask1 is not None and mask1[kps1[ii, 1], kps1[ii, 0]] == 0)
            or (mask2 is not None and mask2[kps2[ii, 1], kps2[ii, 0]] == 0)
        ):
            remove_ids.append(ii)
    kps1 = np.delete(kps1, remove_ids, axis=0)
    kps2 = np.delete(kps2, remove_ids, axis=0)

    if len(kps1) < min_kps:
        img_shape = np.array(mask1.shape)
        # indices = np.meshgrid(np.arange(0, img_shape[0], 50), np.arange(0, img_shape[1], 50), indexing="ij")
        indices = np.where(mask1 > 0)
        indices = np.stack(indices[::-1], axis=-1).reshape(-1, 2)
        add_num = min(len(indices), min_kps - len(kps1))
        add_kps = np.random.choice(np.arange(len(indices)), add_num, replace=False)
        add_kps = indices[add_kps]

        if len(kps1) == 0:
            kps1 = add_kps
            kps2 = add_kps
        else:
            kps1 = np.concatenate((kps1, add_kps), axis=0)
            kps2 = np.concatenate((kps2, add_kps), axis=0)
    return kps1, kps2


def extract_SURF(img, hessianThreshold=4000):
    detector = cv2.xfeatures2d.SURF_create(hessianThreshold=hessianThreshold)
    # detector = cv2.xfeatures2d.SIFT_create(nOctaveLayers=1, contrastThreshold=0.1)
    # detector = cv2.ORB_create()
    kps, des = detector.detectAndCompute(img, None)
    return kps, des


def pack_SURF(keypoints, descriptors):
    if len(keypoints) == 0:
        return np.array([]), np.array([])

    kps = np.array([[kp.pt[0], kp.pt[1], kp.size, kp.angle, kp.response, kp.octave, kp.class_id] for kp in keypoints])
    desc = np.array(descriptors)
    return kps, desc


def unpack_SURF(kps, des):
    try:
        kps = [
            cv2.KeyPoint(x, y, _size, _angle, _response, int(_octave), int(_class_id))
            for x, y, _size, _angle, _response, _octave, _class_id in list(kps)
        ]
        return kps, np.array(des)
    except (IndexError):
        return [], np.array([])


def save_SURF(fname, kps, des):
    kps, des = pack_SURF(kps, des)
    mkdir(osp.dirname(fname))
    try:
        sio.savemat(fname, {"kps": kps, "des": des})
    except TypeError as err:
        print(kps, des)
        raise


def load_SURF(fname):
    """Read feature properties and return in matrix form."""
    if os.path.getsize(fname) <= 0:
        return np.array([]), np.array([])

    data = sio.loadmat(fname)
    kps, des = unpack_SURF(data["kps"], data["des"])
    return kps, des  # keypoint locations, descriptors


if __name__ == "__main__":
    prefix = ""
