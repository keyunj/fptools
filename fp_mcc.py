"""
This file (mcc.py) is designed for:
    MCC (Minutia Cylinder-Code) related functions
Copyright (c) 2021, Yongjie Duan. All rights reserved.
"""
import os
import sys

# os.chdir(sys.path[0])
import os.path as osp
import numpy as np
from glob import glob
import scipy.linalg as slg
import scipy.io as sio
import scipy.stats as sst
from scipy.ndimage import map_coordinates
from scipy.spatial import ConvexHull, distance
from skimage import morphology
import cv2
import time
from PIL import Image, ImageDraw

sys.path.append(osp.dirname(osp.abspath(__file__)))
from uni_io import mkdir
import fp_verifinger


def load_mcc_feature(fpath):
    des = sio.loadmat(fpath)
    des["flag"] = des["flag"].flatten()
    des["neighbor"] = des["neighbor"].flatten()
    return des


def poly2mask(polygon, img_shape):
    """polygon to mask image

    Parameters:
        polygon: [N,2]
        img_shape: (width, height)
    Returns:
        [None]
    """
    mask = Image.new("L", img_shape, 0)
    ImageDraw.Draw(mask).polygon(polygon.reshape(-1).tolist(), outline=1, fill=1)
    return np.array(mask)


class MCCParameters:
    def __init__(
        self,
        omega=None,
        sigma_s=None,
        sigma_d=None,
        R=None,
        Ns=None,
        Nd=None,
        tau_psi=None,
        mu_psi=None,
        is_binary=False,
        thresholds={
            "range": np.arange(0, 211, 30),
            "min_dist": np.arange(0.52, 0.71, 0.03),
            "max_angle": np.arange(34, 47, 2),
            "max_rangle": np.arange(35, 66, 5),
        },
    ) -> None:
        self.is_binary = is_binary
        self.thresholds = thresholds

        if self.is_binary:
            self.omega = omega if omega is not None else 50
            self.sigma_s = sigma_s if sigma_s is not None else 28 / 3
            self.sigma_d = sigma_d if sigma_d is not None else 2 * np.pi / 9
            self.R = R if R is not None else 70
            self.Ns = Ns if Ns is not None else 8
            self.Nd = Nd if Nd is not None else 6
            self.tau_psi = tau_psi if tau_psi is not None else 400
            self.mu_psi = mu_psi if mu_psi is not None else 0.005

            self.min_VC = 0.5  # 0.75
            self.min_M = 1

            self.n_func = 32
            self.n_select = 24
            self.n_bits = 312
            self.p = 30
            self.n_minpc = 2
            self.key_dtype = np.uint32
        else:
            self.omega = omega if omega is not None else 70
            self.sigma_s = sigma_s if sigma_s is not None else 7
            self.sigma_d = sigma_d if sigma_d is not None else 0.37
            self.R = R if R is not None else 70
            self.Ns = Ns if Ns is not None else 15
            self.Nd = Nd if Nd is not None else 6
            self.tau_psi = tau_psi if tau_psi is not None else 406
            self.mu_psi = mu_psi if mu_psi is not None else 0.0045

            self.min_VC = 0.3  # 0.75
            self.min_M = 1
            self.min_ME = 0.3  # 0.6
            self.delta_theta = 3 * np.pi / 4
            self.min_pair = 4
            self.max_pair = 10
            self.mu_p = 32
            self.tau_p = 0.25

        self.radius_s = 3 * self.sigma_s
        self.delta_s = 2 * self.R / self.Ns
        self.delta_d = 2 * np.pi / self.Nd

        # self.disk_omega = morphology.disk(omega + 2 * (4 - 1))[7:-7, 7:-7]
        self.disk_omega = morphology.disk(self.omega)[1:-1, 1:-1]

        grid = np.stack(np.meshgrid(np.arange(self.Ns), np.arange(self.Ns)), axis=0) + 1 - (self.Ns + 1) / 2
        self.X0, self.Y0 = self.delta_s * grid
        self.mask = np.sqrt(self.X0 ** 2 + self.Y0 ** 2) <= self.R
        self.cell_num = self.mask.sum()

        self.d_phi = np.arange(0.5, self.Nd) * self.delta_d - np.pi  # [-pi, pi]


class MCC(MCCParameters):
    def __init__(
        self,
        omega=None,
        sigma_s=None,
        sigma_d=None,
        R=None,
        Ns=None,
        Nd=None,
        tau_psi=None,
        mu_psi=None,
        is_binary=False,
        thresholds={
            "range": np.arange(0, 211, 30),
            "min_dist": np.arange(0.52, 0.71, 0.03),
            "max_angle": np.arange(34, 47, 2),
            "max_rangle": np.arange(35, 66, 5),
        },
    ) -> None:
        super().__init__(omega, sigma_s, sigma_d, R, Ns, Nd, tau_psi, mu_psi, is_binary, thresholds)

    def similarity(self, cur_des1, cur_des2):
        if len(cur_des1[0]["cm"]) == 0 or len(cur_des2[0]["cm"]) == 0:
            return 0

        cur_mnt1 = cur_des1[0]["mnt"]
        cur_mnt2 = cur_des2[0]["mnt"]
        if np.abs(cur_mnt1[2] - cur_mnt2[2]) > self.delta_theta * 180 / np.pi:
            return 0

        mask = cur_des1[0]["mask"] * cur_des2[0]["mask"]
        if mask.sum() < self.min_ME * np.size(mask):
            return 0

        c1 = cur_des1[0]["cm"][mask.reshape(-1)].reshape(-1)
        c2 = cur_des2[0]["cm"][mask.reshape(-1)].reshape(-1)
        temp = np.linalg.norm(c1) + np.linalg.norm(c2)
        if temp == 0:
            return 0
        else:
            return 1 - np.linalg.norm(c1 - c2) / temp

    def compute_similarity_matrix(self, des1, des2):
        """compute similarity between two minutiae

        Parameters:
            [None]
        Returns:
            [None]
        """
        # return distance.cdist(des1, des2, self.similarity)
        N1 = len(des1["flag"])
        N2 = len(des2["flag"])

        cm_mask = des1["flag"][:, None] * des2["flag"][None]

        delta = (des1["mnt"][:, 2][:, None] - des2["mnt"][:, 2][None] + 180) % 360 - 180
        mnt_mask = np.abs(delta) <= (self.delta_theta * 180 / np.pi)

        mask = des1["mask"][:, None] * des2["mask"][None]
        mask_mask = mask.sum(axis=-1) >= (self.min_ME * (self.Ns ** 2))

        c1 = (des1["cm"][:, None] * mask[..., None]).reshape(N1, N2, -1)
        c2 = (des2["cm"][None] * mask[..., None]).reshape(N1, N2, -1)
        temp = slg.norm(c1, axis=-1, check_finite=False) + slg.norm(c2, axis=-1, check_finite=False)
        temp_mask = temp != 0

        S = 1 - slg.norm(c1 - c2, axis=-1, check_finite=False) / temp.clip(1e-24, None)
        S = S * cm_mask * mnt_mask * mask_mask * temp_mask
        return S

    def compute_binary_relation_fast(self, mnts):
        x1 = mnts[:, 0:1]
        y1 = mnts[:, 1:2]
        angle1 = 360 - mnts[:, 2:3]
        temp = np.arctan2(y1 - y1.T, x1.T - x1) * 180 / np.pi
        angle = normalize_minu_dir(temp - angle1)
        t_angle = np.triu(angle, 1)
        angle = t_angle + t_angle.T

        r_angle = normalize_minu_dir(angle1.T - angle1)
        dist = distance.squareform(distance.pdist(mnts[:, :2]))
        return dist, angle, r_angle

    def fingerprint_matching_single(
        self,
        dir1,
        name1,
        dir2,
        name2,
        img_shape1=(800, 750),
        img_shape2=(800, 750),
        mask1=None,
        mask2=None,
        is_save1=False,
        is_save2=False,
        fpath1=None,
        fpath2=None,
    ):
        mnts1 = fp_verifinger.load_minutiae(osp.join(dir1, name1 + ".mnt"))
        mnts2 = fp_verifinger.load_minutiae(osp.join(dir2, name2 + ".mnt"))
        des1 = self.create_descriptor(mnts1, img_shape1, mask=mask1, is_save=is_save1, fpath=fpath1)
        des2 = self.create_descriptor(mnts2, img_shape2, mask=mask2, is_save=is_save2, fpath=fpath2)
        score, pairs = self.fingerprint_matching(mnts1, mnts2, des1, des2)
        return score, pairs

    def fingerprint_matching(self, mnts1, mnts2, des1, des2):
        """
        Parameters:
            [None]
        Returns:
            score, pairs
        """
        try:
            # end = time.time()
            S = self.compute_similarity_matrix(des1, des2)
            # end = time.time() - end
            # print(f"=> similarity time: {end:.3f}s")

            th = 0
            # top max_n for each mnt1
            max_n = min(2, S.shape[1])
            indices11 = np.arange(S.shape[0]).repeat(max_n, axis=-1).reshape(-1)
            indices21 = np.argsort(S, axis=1)[:, : -max_n - 1 : -1].reshape(-1)
            idx_mask = S[indices11, indices21] > th
            indices11 = indices11[idx_mask]
            indices21 = indices21[idx_mask]
            # top max_n for each mnt2
            max_n = min(2, S.shape[0])
            indices12 = np.argsort(S, axis=0)[: -max_n - 1 : -1, :].reshape(-1)
            indices22 = np.arange(S.shape[1])[None].repeat(max_n, axis=0).reshape(-1)
            idx_mask = S[indices12, indices22] > th
            indices12 = indices12[idx_mask]
            indices22 = indices22[idx_mask]
            # combination
            indices1 = np.concatenate((indices11, indices12))
            indices2 = np.concatenate((indices21, indices22))
            indices = list(set([(x1, x2) for x1, x2 in zip(indices1, indices2)]))
            indices1, indices2 = map(list, zip(*indices))
            indices1 = np.array(indices1)
            indices2 = np.array(indices2)

            argidx = np.argsort(indices1 + indices2)
            indices1 = indices1[argidx]
            indices2 = indices2[argidx]

            n = len(indices1)
            if n <= 3:
                print(f"=> few matches found")
                return 0, np.array([])
            dist1, angle1, r_angle1 = self.compute_binary_relation_fast(mnts1[indices1])
            dist2, angle2, r_angle2 = self.compute_binary_relation_fast(mnts2[indices2])
            dist_range = np.maximum(
                1,
                np.minimum(
                    len(self.thresholds["range"]) - 1,
                    np.ceil(np.minimum(dist1, dist2) / (self.thresholds["range"][1] - self.thresholds["range"][0])),
                ),
            ).astype(int)
            ratio = np.minimum(dist1, dist2) / np.maximum(dist1, dist2).clip(1e-24, None)
            dist_s = (ratio - self.thresholds["min_dist"][dist_range - 1]) / (
                1 - self.thresholds["min_dist"][dist_range - 1]
            )
            dist_s = dist_s.clip(0, None)

            angle_s = 1 - np.abs(normalize_minu_dir(angle1 - angle2)) / self.thresholds["max_angle"][dist_range - 1]
            angle_s = angle_s.clip(0, None)

            r_angle_s = 1 - np.abs(normalize_minu_dir(r_angle1 - r_angle2)) / self.thresholds["max_rangle"][dist_range - 1]
            r_angle_s = r_angle_s.clip(0, None)

            M = dist_s * angle_s * r_angle_s
            zero_mask = (indices1[:, None] == indices1[None]) | (indices2[:, None] == indices2[None])
            M[zero_mask] = 0
            # for ii in range(n):
            #     M[ii, (indices1 == indices1[ii]) | (indices2 == indices2[ii])] = 0

            # principal eigenvector
            w, v = slg.eigh(M, subset_by_index=(n - 1, n - 1))
            v = np.abs(v.reshape(-1))
            v_idx = np.argsort(v)[::-1]
            flag_match1 = np.zeros(len(mnts1))
            flag_match2 = np.zeros(len(mnts2))
            pair_ids = []
            for ii in range(n):
                if v[v_idx[ii]] <= 0.00001:
                    break
                if flag_match1[indices1[v_idx[ii]]] or flag_match2[indices2[v_idx[ii]]]:
                    continue
                if len(pair_ids) and len(np.where(M[pair_ids, v_idx[ii]] == 0)[0]):
                    continue
                pair_ids.append(v_idx[ii])
                flag_match1[indices1[v_idx[ii]]] = 1
                flag_match2[indices2[v_idx[ii]]] = 1
            pairs = np.stack((indices1[pair_ids], indices2[pair_ids]), axis=-1)
            score = M[np.ix_(pair_ids, pair_ids)].sum()
        except:
            score = 0
            pairs = np.array([])
        return score, pairs

    def create_descriptor(self, mnts, img_shape, mask=None, is_save=False, fpath=None):
        """create MCC descriptor for input minutia

        Parameters:
            mnts: [N,3] or [N,4]
            img_shape: (width, height)
        Returns:
            [None]
        """
        # convex hull of minutiae, dilated mask
        convex_hull = ConvexHull(mnts[:, :2])
        ROI = poly2mask(mnts[convex_hull.vertices, :2], tuple(img_shape))
        ROI = ROI * mask if mask is not None else ROI
        ROI = cv2.dilate(ROI, self.disk_omega)

        # distance map for each pair of minutiae
        mnt_dist_map = distance.squareform(distance.pdist(mnts[:, :2]))
        mnt_dist_map[np.diag_indices_from(mnt_dist_map)] = 10000

        N = len(mnts)
        descriptor = {
            "mnt": mnts,
            "flag": np.zeros(N, dtype=bool),
            "cm": np.zeros((N, self.Ns ** 2, self.Nd)),
            "mask": np.zeros((N, self.Ns ** 2), dtype=bool),
            "neighbor": np.zeros(N),
        }

        # for each minutia
        for cur_ii, cur_mnt in enumerate(mnts):
            # rotate disk around current minutia
            sin_ori = np.sin(cur_mnt[2] * np.pi / 180)
            cos_ori = np.cos(cur_mnt[2] * np.pi / 180)
            X = cur_mnt[0] + cos_ori * self.X0 - sin_ori * self.Y0
            Y = cur_mnt[1] + sin_ori * self.X0 + cos_ori * self.Y0
            # disk_mask = self.mask * (X > 0) * (X < img_shape[0]) * (Y > 0) * (Y < img_shape[1])
            disk_mask = self.mask * map_coordinates(ROI * 1, np.stack((Y, X)), order=0) > 0
            if disk_mask.sum() < (self.min_VC * self.cell_num):
                continue

            # distance map between current point and minutia within_mask local disk
            cur_dist = mnt_dist_map[cur_ii]
            within_mask = cur_dist <= (self.R + self.radius_s)
            if within_mask.sum() < self.min_M:
                continue

            # spatial contribution
            local_Ds = distance.cdist(np.stack((X, Y), axis=-1).reshape(-1, 2), mnts[within_mask, :2])
            Cs = np.exp(-(local_Ds ** 2) / (2 * self.sigma_s ** 2)) / (np.sqrt(2 * np.pi) * self.sigma_s)
            Cs *= 1 * (local_Ds <= self.radius_s) * disk_mask.reshape(-1, 1)
            # orientation contribution
            local_Dd = normalize_minu_dir((mnts[within_mask, 2] - cur_mnt[2]), edge=180) * np.pi / 180
            local_Dd = normalize_minu_dir(local_Dd[:, None] - self.d_phi[None], edge=np.pi)
            d = sst.norm(loc=0, scale=self.sigma_d)
            cdf1 = d.cdf(local_Dd - self.delta_d / 2)
            cdf2 = d.cdf(local_Dd + self.delta_d / 2)
            Cd = cdf2 - cdf1
            # Cd = np.exp(-(local_Dd ** 2) / (2 * self.sigma_d ** 2)) / (np.sqrt(2 * np.pi) * self.sigma_d)
            # normalizing the contribution
            Cm = (Cs[:, :, None] * Cd[None, :, :]).sum(axis=1)
            if self.is_binary:
                Cm = Cm > self.mu_psi
            else:
                Cm = 1.0 / (1 + np.exp(-self.tau_psi * (Cm - self.mu_psi)))

            descriptor["flag"][cur_ii] = 1
            descriptor["cm"][cur_ii] = Cm
            descriptor["mask"][cur_ii] = disk_mask.reshape(-1)
            descriptor["neighbor"][cur_ii] = within_mask.sum()

        if self.is_binary:
            descriptor["cm"] = (
                np.transpose(descriptor["cm"].reshape(N, self.Ns, self.Ns, -1), (0, 3, 1, 2))[:, :, self.mask > 0]
                .reshape(N, -1)
                .astype(bool)
            )

        if is_save and fpath is not None:
            mkdir(osp.dirname(fpath))
            sio.savemat(fpath, descriptor)
        return descriptor


def normalize_minu_dir(angle_rad, edge=180):
    return (angle_rad + edge) % (2 * edge) - edge


def fingerprint_matching_single(search_path, gallery_path, search_mcc_path=None, gallery_mcc_path=None):
    """
    Parameters:
        [None]
    Returns:
        score [, pairs]
    """
    search_mnt, search_header = fp_verifinger.load_minutiae(search_path + ".mnt", True)
    gallery_mnt, gallery_header = fp_verifinger.load_minutiae(gallery_path + ".mnt", True)

    if search_mcc_path is not None:
        search_mcc = load_mcc_feature(search_mcc_path)
    else:
        search_mcc = MCC().create_descriptor(search_mnt, search_header)
    if gallery_mcc_path is not None:
        gallery_mcc = load_mcc_feature(gallery_mcc_path)
    else:
        gallery_mcc = MCC().create_descriptor(gallery_mnt, gallery_header)

    return MCC().fingerprint_matching(search_mnt, gallery_mnt, search_mcc, gallery_mcc)


if __name__ == "__main__":
    tool_mcc = MCC()

    img_name1 = "1000"
    img_name2 = "1000"

    mnt_type = "neu"

    mnts1, img_shape1 = fp_verifinger.load_minutiae(
        f"/home/dyj/disk1/data/finger/Hisign/latent/feature/mnt/manual/{img_name1}.mnt", return_hearder=True
    )
    des1 = tool_mcc.create_descriptor(
        mnts1,
        img_shape1,
        is_save=True,
        fpath=f"/home/dyj/disk1/data/finger/Hisign/latent/feature/mnt/mcc/{img_name1}.mat",
    )

    mnts2, img_shape2 = fp_verifinger.load_minutiae(
        f"/home/dyj/disk1/data/finger/Hisign/file/feature/mnt/{mnt_type}/{img_name2}.mnt", return_hearder=True
    )
    des2 = tool_mcc.create_descriptor(
        mnts2,
        img_shape2,
        is_save=True,
        fpath=f"/home/dyj/disk1/data/finger/Hisign/file/feature/mnt/mcc/{img_name2}.mat",
    )

    score, pairs = tool_mcc.fingerprint_matching(mnts2, mnts1, des2, des1)
    kps_q = mnts1[pairs[:, 1]].astype(np.float32)
    kps_t = mnts2[pairs[:, 0]].astype(np.float32)

    _, status = cv2.estimateAffinePartial2D(
        kps_t[:, None, :2], kps_q[:, None, :2], method=cv2.RANSAC, ransacReprojThreshold=25
    )
    pairs = pairs[status[:, 0] > 0]
    kps_q = kps_q[status[:, 0] > 0]
    kps_t = kps_t[status[:, 0] > 0]

    print(f"=> score: {score} of {len(pairs)} pairs / ({len(mnts1)} vs {len(mnts2)})")

    import imageio
    import matplotlib.pyplot as plt
    from matplotlib.patches import ConnectionPatch

    img1 = imageio.imread(f"/home/dyj/disk1/data/finger/Hisign/latent/image/{img_name1}.bmp")
    img2 = imageio.imread(f"/home/dyj/disk1/data/finger/Hisign/file/image/{img_name2}.bmp")

    length = 20

    fig = plt.figure()
    ax1 = fig.add_subplot(121)
    ax2 = fig.add_subplot(122)
    ax1.imshow(img1, "gray")
    ax2.imshow(img2, "gray")

    for cur_kp in mnts1:
        ax1.plot(cur_kp[0], cur_kp[1], "bs", markersize=3, markerfacecolor="none")
        ax1.plot(
            [cur_kp[0], cur_kp[0] + length * np.cos(cur_kp[2] * np.pi / 180)],
            [cur_kp[1], cur_kp[1] + length * np.sin(cur_kp[2] * np.pi / 180)],
            linewidth=1.0,
            color="b",
        )
    for cur_kp in mnts2:
        ax2.plot(cur_kp[0], cur_kp[1], "bs", markersize=3, markerfacecolor="none")
        ax2.plot(
            [cur_kp[0], cur_kp[0] + length * np.cos(cur_kp[2] * np.pi / 180)],
            [cur_kp[1], cur_kp[1] + length * np.sin(cur_kp[2] * np.pi / 180)],
            linewidth=1.0,
            color="b",
        )

    for ii in range(len(kps_q)):
        kp_t = kps_t[ii, :3]
        kp_q = kps_q[ii, :3]

        con = ConnectionPatch(
            xyA=kp_q[:2], xyB=kp_t[:2], coordsA="data", coordsB="data", axesA=ax1, axesB=ax2, color="green"
        )
        ax2.add_artist(con)

    ax1.axis("off")
    ax2.axis("off")

    plt.savefig("test/search_kps.png")
