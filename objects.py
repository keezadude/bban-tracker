import cv2
import numpy as np

# -------------------------------------------------------------
# Runtime-tweakable constant: position smoothing factor (0–1).
# Exposed via set_smoothing_alpha() so the GUI can provide a
# live slider for power users to fine-tune tracking latency vs
# stability without restarting the application.
# -------------------------------------------------------------

SMOOTH_ALPHA: float = 0.2  # default 20 % new measurement weight


def set_smoothing_alpha(alpha: float):
    """Update global exponential smoothing factor used by Bey.

    Args:
        alpha: value in the inclusive range [0,1]. Values outside will be
                clamped silently.
    """
    global SMOOTH_ALPHA
    alpha = max(0.0, min(1.0, float(alpha)))
    SMOOTH_ALPHA = alpha

class Contour:
    def __init__(self, contour):
        self.contour = contour
    
    def getPos(self) -> tuple[int, int]:
        x, y, w, h = cv2.boundingRect(self.contour)
        return (int(x + w/2), int(y + h/2))
    
    def getShape(self) -> tuple[int, int]:
        x, y, w, h = cv2.boundingRect(self.contour)
        return (w, h)
    
    def getBoundingRect(self) -> tuple[int, int, int, int]:
        x, y, w, h = cv2.boundingRect(self.contour)
        return (x, y, w, h)
    
    def getArea(self) -> int:
        x, y, w, h = cv2.boundingRect(self.contour)
        return w * h

    def getContour(self):
        return self.contour
    
class _SimpleKalman:
    """Constant-velocity Kalman filter (state = [x, y, vx, vy])."""

    def __init__(self, x: float, y: float):
        # State vector
        self.x = np.array([[x], [y], [0.0], [0.0]], dtype=float)

        # Covariance matrix – start with large uncertainty in velocity
        self.P = np.diag([1.0, 1.0, 1000.0, 1000.0])

        # Process (motion) noise covariance
        q_pos = 1e-2  # position process noise
        q_vel = 1e-1  # velocity process noise
        self.Q = np.diag([q_pos, q_pos, q_vel, q_vel])

        # Measurement matrix: we observe only position
        self.H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=float)

        # Measurement noise covariance (pixels)
        r = 10.0
        self.R = np.diag([r, r])

        # Identity
        self._I = np.eye(4)

    def predict(self, dt: float = 1.0):
        """Predict next state with timestep *dt* (frames)."""
        F = np.array([[1, 0, dt, 0], [0, 1, 0, dt], [0, 0, 1, 0], [0, 0, 0, 1]], dtype=float)
        self.x = F @ self.x
        self.P = F @ self.P @ F.T + self.Q

    def update(self, meas_x: float, meas_y: float):
        """Update state with a new measurement (pixel coords)."""
        z = np.array([[meas_x], [meas_y]], dtype=float)
        y = z - self.H @ self.x                      # innovation
        S = self.H @ self.P @ self.H.T + self.R      # innovation covariance
        K = self.P @ self.H.T @ np.linalg.inv(S)      # Kalman gain
        self.x = self.x + K @ y
        self.P = (self._I - K @ self.H) @ self.P

    def get_state(self) -> tuple[float, float, float, float]:
        return tuple(self.x.flatten())

class Bey:
    def __init__(self, contour:Contour, base_pos:tuple[int, int]=(0,0)):
        self.frame : int

        x, y, w, h = contour.getBoundingRect()
        x0, y0 = base_pos
        self.x : int = int(x + w/2 + x0)
        self.y : int = int(y + h/2 + y0)
        self.w : int = w
        self.h : int = h

        self.vx : float = 0
        self.vy : float = 0
        self.raw_vx : float = 0
        self.raw_vy : float = 0
        self.ax : float = 0
        self.ay : float = 0
        
        self.id : int

        # ---------------- Kalman filter ---------------- #
        self._kf = _SimpleKalman(self.x, self.y)

        # raw velocity defaults remain zero on first frame; filter will be
        # updated after association via setPreBey().
        
    def __str__(self):
        id = self.getId()
        x, y = self.getPos()
        return str((id, x, y))
    
    def setPreBey(self, pre_bey:'Bey'):
        #idを設定
        self.id = pre_bey.getId()

        # ---------------- Kalman update ---------------- #
        meas_x, meas_y = self.getPos()
        pre_x, pre_y = pre_bey.getPos()
        dt = max(1, self.getFrame() - pre_bey.getFrame())

        # Continue using the previous Kalman filter instance
        self._kf = pre_bey._kf  # type: ignore[attr-defined]
        self._kf.predict(dt=dt)
        self._kf.update(meas_x, meas_y)

        kx, ky, kvx, kvy = self._kf.get_state()

        # ----------------------------------------------------------
        # Exponential Smoothing (user-tunable)
        # ----------------------------------------------------------
        # The GUI exposes a "Position Smoothing" slider (0–100 %) that
        # updates the global constant ``SMOOTH_ALPHA`` at runtime via
        # objects.set_smoothing_alpha().  The value represents the weight
        # of the **new** measurement (alpha = 1 → no smoothing, alpha = 0
        # → fully rely on the previous filtered state).
        #
        # By blending the freshly updated Kalman estimate (kx, ky) with the
        # raw measurement (meas_x, meas_y) we allow the operator to trade
        # responsiveness for stability without having to fiddle with the
        # Kalman noise matrices directly.
        # ----------------------------------------------------------
        alpha = SMOOTH_ALPHA  # range [0,1] – new measurement weight

        # Blend **measurement** with **Kalman estimate**
        self.x = int((1.0 - alpha) * kx + alpha * meas_x)
        self.y = int((1.0 - alpha) * ky + alpha * meas_y)

        # Update kinematic attributes
        self.raw_vx = (meas_x - pre_x) / dt
        self.raw_vy = (meas_y - pre_y) / dt
        self.vx = float(kvx)
        self.vy = float(kvy)

        self.ax = (self.vx - pre_bey.vx) / dt
        self.ay = (self.vy - pre_bey.vy) / dt
    
    def getFrame(self) -> int:
        return self.frame
    
    def setFrame(self, frame:int):
        self.frame = frame
    
    def getPos(self) -> tuple[int, int]:
        return (self.x, self.y)
    
    def getVel(self) -> tuple[float, float]:
        return (self.vx, self.vy)
    
    def getRawVel(self) -> tuple[float, float]:
        return (self.raw_vx, self.raw_vy)
    
    def getAcc(self) -> tuple[float, float]:
        return (self.ax, self.ay)
    
    def estimatePos(self) -> tuple[int, int]:
        x0, y0 = self.getPos()
        v0x, v0y = self.getVel()
        ax, ay = self.getAcc()
        t = 10
        x = int(x0 + v0x*t + 0.5*ax*t*t)
        y = int(y0 + v0y*t + 0.5*ay*t*t)
        return (x, y)
    
    def getShape(self) -> tuple[int, int]:
        return (self.w, self.h)
    
    def getRect(self) -> tuple[tuple[int, int], tuple[int, int]]:
        x, y = self.getPos()
        w, h = self.getShape()
        pos1 = (int(x - w/2), int(y - h/2))
        pos2 = (int(x + w/2), int(y + h/2))
        return (pos1, pos2)
    
    def getId(self) -> int:
        return self.id
    
    def setId(self, id:int):
        self.id = id

class Hit:
    def __init__(self, bey1:Bey, bey2:Bey):
        self.bey1 : Bey = bey1
        self.bey2 : Bey = bey2

        self.w : int
        self.h : int

        self.is_new_hit : bool
    
    def __str__(self):
        return str(self.getPos())
    
    def getBeys(self) -> tuple[Bey, Bey]:
        return self.bey1, self.bey2
    
    def getPos(self) -> tuple[int, int]:
        x1, y1 = self.bey1.getPos()
        x2, y2 = self.bey2.getPos()
        return (int((x1+x2)/2), int((y1+y2)/2))
    
    def getShape(self) -> tuple[int, int]:
        return (self.w, self.h)
    
    def setShape(self, shape:tuple[int, int]):
        self.w, self.h = shape
    
    def getRect(self) -> tuple[tuple[int, int], tuple[int, int]]:
        x, y = self.getPos()
        w, h = self.getShape()
        pos1 = (int(x - w/2), int(y - h/2))
        pos2 = (int(x + w/2), int(y + h/2))
        return (pos1, pos2)
    
    def isNewHit(self) -> bool:
        return self.is_new_hit
    
    def setIsNewHit(self, is_new_hit:bool):
        self.is_new_hit = is_new_hit
    
    def getTag(self) -> int:
        bey1, bey2 = self.getBeys()
        id1 = bey1.getId()
        id2 = bey2.getId()
        if id1 < id2:
            return (id1, id2)
        else:
            return (id2, id1)
    

