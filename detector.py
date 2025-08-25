import cv2

class PeopleDetector:
    # Default OpenCV HOG person detector (no external downloads).
    def __init__(self, model_path: str = ""):
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    def infer(self, frame):
        # returns list of (x1,y1,x2,y2,conf)
        rects, weights = self.hog.detectMultiScale(frame, winStride=(8,8), padding=(8,8), scale=1.05)
        boxes = []
        for (x, y, w, h), conf in zip(rects, weights):
            boxes.append((int(x), int(y), int(x+w), int(y+h), float(conf)))
        return boxes

    def draw(self, frame, boxes):
        for (x1,y1,x2,y2,conf) in boxes:
            cv2.rectangle(frame, (x1,y1), (x2,y2), (0,255,0), 2)
        return frame
