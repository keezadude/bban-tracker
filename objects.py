import cv2

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
    
    def __str__(self):
        id = self.getId()
        x, y = self.getPos()
        return str((id, x, y))
    
    def setPreBey(self, pre_bey:'Bey'):
        #idを設定
        self.id = pre_bey.getId()

        #速度を計算
        x, y = self.getPos()
        pre_x, pre_y = pre_bey.getPos()
        dt = self.getFrame() - pre_bey.getFrame()
        vx, vy = (x - pre_x)/dt, (y - pre_y)/dt
        self.raw_vx = vx
        self.raw_vy = vy

        #速度を平滑化
        pre_vx, pre_vy = pre_bey.getVel()
        self.vx = 0.05*vx + 0.95*pre_vx
        self.vy = 0.05*vy + 0.95*pre_vy

        pre_ax, pre_ay = pre_bey.getAcc()
        pre_raw_vx , pre_raw_vy = pre_bey.getRawVel()
        ax = (vx - pre_raw_vx)/dt
        ay = (vy - pre_raw_vy)/dt
        self.ax = 0.05*ax + 0.95*pre_ax
        self.ay = 0.05*ay + 0.95*pre_ay
    
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
    

