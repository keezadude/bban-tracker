import json
from pathlib import Path
import numpy as np
import cv2
import itertools
from objects import Contour, Bey, Hit
import math

# Path where CalibrationWizard persists the last-used profile
_CONFIG_DIR = Path.home() / ".beytracker"
_CALIB_PROFILE_FILE = _CONFIG_DIR / "calibration_profiles.json"

def _load_profile():
    """Return dict with persisted calibration values or empty dict if none."""
    try:
        if _CALIB_PROFILE_FILE.exists():
            with _CALIB_PROFILE_FILE.open("r", encoding="utf-8") as fp:
                return json.load(fp).get("last", {})
    except Exception:
        # On any failure we fall back to defaults silently
        pass
    return {}

class Detector:
    def __init__(self):
        # ---- Defaults ---- #
        self.threshold = 15
        self.min_contour_area = 100  # formerly hard-coded lower bound
        self.large_contour_area = 2000  # formerly threshold for split

        # ---- Apply persisted profile if available ---- #
        prof = _load_profile()
        self.threshold = int(prof.get("threshold", self.threshold))
        self.min_contour_area = int(prof.get("min_area", self.min_contour_area))
        self.large_contour_area = int(prof.get("max_area", self.large_contour_area))

    def calibrate(self, getImage):
        #背景画像の設定
        imgs = []
        for i in range(120):
            ir_img = getImage()
            imgs.append(ir_img)
            print(f"\rcalibration {len(imgs)} / 120", end="")
        imgs = np.stack(imgs)
        self.mean_img = np.mean(imgs, axis=0)
        self.std_img = np.std(imgs, axis=0) + 1e-16
        print("")
    
    def detect(self, ir_img:np.ndarray) -> tuple[list[Bey], list[Hit]]:
        
        z = (ir_img - self.mean_img) / self.std_img
        thresh = np.zeros_like(ir_img, dtype = np.uint8)
        thresh[z >= self.threshold] = 255

        #cv2.imshow("thresh", thresh)
        kernel = np.ones((3,3),np.uint8)
        opening = cv2.morphologyEx(thresh,cv2.MORPH_OPEN,kernel, iterations = 2)
        #cv2.imshow("opening", opening)

        #コマ、衝突箇所の座標を取得
        beys, hits = self.__getObjects(opening.astype(np.uint8))

        return beys, hits
    
    
    def __getObjects(self, img:np.ndarray) -> tuple[list[Bey], list[Hit]]:
        dist_transform = cv2.distanceTransform(img, cv2.DIST_L2,5)
        ret, sure_fg = cv2.threshold(dist_transform, 0.8*dist_transform.max(), 255, 0)

        _contours, hierarchy = cv2.findContours(img, cv2.RETR_LIST, cv2.CHAIN_APPROX_TC89_KCOS)
        contours = [Contour(contour) for contour in _contours]
        
        beys:list[Bey] = []
        hits:list[Hit] = []

        for contour in contours:
            #小さすぎるものは認識しない
            area = contour.getArea()
            if area < self.min_contour_area:
                pass
            #面積が250以上2000未満のものはコマ1つとして認識
            elif area < self.large_contour_area:
                bey = Bey(contour)
                beys.append(bey)
            
            #面積が2000以上のときは複数のコマがつながっていると判断して切り分ける
            else:
                x, y, w, h = contour.getBoundingRect()
                _sure_contours, hierarchy = cv2.findContours(sure_fg[y:y+h, x:x+w].astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_TC89_KCOS)
                sure_contours = [Contour(contour) for contour in _sure_contours]
                sure_beys = [Bey(s_contour, base_pos=(x, y)) for s_contour in sure_contours if (s_contour.getArea() < self.large_contour_area)]
                beys += sure_beys
        
        hits = []
        for bey1, bey2 in itertools.combinations(beys, 2):
            if math.dist(bey1.getPos(), bey2.getPos()) < 40:
                hit = Hit(bey1, bey2)
                hit.setShape((2*abs(bey1.x - bey2.x), 2*abs(bey1.y - bey2.y)))
                hits.append(hit)
                
        return beys, hits